"""Write operations on the issue graph.

Every public function here is a complete unit of work: it validates its input,
applies the change, records an audit event, and returns a JSON-safe dict.
Functions compose freely because they all acquire the session through
`auto_session()`, so calling one from inside another joins the caller's
transaction rather than opening a competing one.

Design notes
------------
* Hierarchy is an edge, not a column. A child points at its parent through a
  `parent-child` dependency row, so containment and blocking are queried by
  the same mechanism and an issue can be re-parented without touching it.
* Only `blocks` edges gate execution; see `database.domain`.
* `blocks` and `parent-child` edges are kept acyclic. A blocking cycle would
  make every issue in it permanently unstartable, and a parent-child cycle
  would make the hierarchy walk non-terminating.
"""

from __future__ import annotations

from typing import Any, Iterable, Literal, TypedDict

from sqlalchemy import select

from ..db_client import auto_session
from ..domain import (
    DEFAULT_PRIORITY,
    DEP_BLOCKS,
    DEP_PARENT_CHILD,
    STATUS_CLOSED,
    STATUS_IN_PROGRESS,
    STATUS_OPEN,
    TYPE_EPIC,
    TYPE_TASK,
    ValidationError,
    normalize_labels,
    validate_dependency_type,
    validate_estimated_minutes,
    validate_issue_type,
    validate_priority,
    validate_status,
    validate_title,
)
from ..models import Comment, Dependency, Event, Issue, Label
from ..serializers import (
    comment_to_dict,
    dependency_to_dict,
    event_to_dict,
    issue_to_dict,
)

__all__ = [
    "IssueKwargs",
    "IssueNotFoundError",
    "DependencyCycleError",
    "create_issue",
    "create_child_issue",
    "create_epic_with_children",
    "add_labels",
    "remove_labels",
    "set_labels",
    "add_dependency",
    "remove_dependency",
    "add_comment",
    "update_issue_fields",
    "claim_issue",
    "close_issue",
    "reopen_issue",
    "unassign_issue",
    "add_event",
    "delete_issue",
]


class IssueNotFoundError(ValueError):
    """Raised when an operation names an issue id that does not exist."""


class DependencyCycleError(ValueError):
    """Raised when an edge would introduce a cycle in an acyclic edge type."""


class IssueKwargs(TypedDict, total=False):
    """Field bundle accepted when creating an issue.

    Every key is optional except `title`. Used for the per-child dictionaries
    passed to `create_epic_with_children`.
    """

    title: str
    description: str
    acceptance_criteria: str
    notes: str
    status: str
    priority: int
    issue_type: Literal["task", "subtask", "epic"]
    assignee: str | None
    estimated_minutes: int | None
    created_by: str
    pinned: bool


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _load_issue(session, issue_id: int) -> Issue:
    """Fetch an issue or raise a message naming the id that was missing."""
    issue = await session.get(Issue, issue_id)
    if issue is None:
        raise IssueNotFoundError(f"issue not found: {issue_id}")
    return issue


async def _reaches(session, start_id: int, target_id: int, edge_type: str) -> bool:
    """Return True if `target_id` is reachable from `start_id` along `edge_type`.

    Breadth-first over outgoing edges, tracking visited ids so an existing
    cycle in the data cannot make this loop forever.
    """
    frontier = [start_id]
    visited: set[int] = set()

    while frontier:
        rows = await session.execute(
            select(Dependency.depends_on_id).where(
                Dependency.issue_id.in_(frontier),
                Dependency.type == edge_type,
            )
        )
        next_ids = {row for row in rows.scalars() if row not in visited}
        if target_id in next_ids:
            return True
        visited.update(next_ids)
        frontier = list(next_ids)

    return False


async def _guard_acyclic(
    session, issue_id: int, depends_on_id: int, dep_type: str
) -> None:
    """Reject an edge that would close a loop in an acyclic edge type."""
    if dep_type not in (DEP_BLOCKS, DEP_PARENT_CHILD):
        return

    if await _reaches(session, depends_on_id, issue_id, dep_type):
        raise DependencyCycleError(
            f"adding {dep_type!r} edge {issue_id} -> {depends_on_id} would create a "
            f"cycle; {depends_on_id} already depends on {issue_id}."
        )


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


async def create_issue(
    title: str = "",
    description: str = "",
    acceptance_criteria: str = "",
    notes: str = "",
    status: str = STATUS_OPEN,
    priority: int = DEFAULT_PRIORITY,
    issue_type: Literal["task", "subtask", "epic"] = TYPE_TASK,
    assignee: str | None = None,
    estimated_minutes: int | None = None,
    created_by: str = "",
    pinned: bool = False,
    labels: list[str] | None = None,
    dependencies: list | None = None,
) -> dict[str, Any]:
    """Create an issue, optionally with labels and outgoing dependency edges.

    Args:
        title: Required, non-blank, at most 500 characters.
        status: One of `database.domain.ALL_STATUSES`.
        priority: 0 (highest) through 4 (lowest).
        issue_type: "task", "subtask" or "epic".
        labels: Label strings; duplicates and blanks are dropped.
        dependencies: Pairs of `(depends_on_id, dep_type)` with the new issue
            as the source. Accepts lists as well as tuples so the same shape
            works over JSON.

    Returns:
        The created issue as a JSON-safe dict, including its assigned id.

    Raises:
        ValidationError: A field is outside the tracker's vocabulary.
        IssueNotFoundError: A dependency names an issue that does not exist.
        DependencyCycleError: A dependency would create a cycle.
    """
    clean_title = validate_title(title)
    validate_status(status)
    validate_priority(priority)
    validate_issue_type(issue_type)
    validate_estimated_minutes(estimated_minutes)
    label_list = normalize_labels(labels)

    async with auto_session() as session:
        issue = Issue(
            title=clean_title,
            description=description,
            acceptance_criteria=acceptance_criteria,
            notes=notes,
            status=status,
            priority=priority,
            issue_type=issue_type,
            assignee=assignee,
            estimated_minutes=estimated_minutes,
            created_by=created_by,
            pinned=pinned,
        )
        session.add(issue)
        await session.flush()  # assigns issue.id

        if label_list:
            await add_labels(issue.id, label_list)

        for depends_on_id, dep_type in dependencies or []:
            await add_dependency(
                issue.id,
                int(depends_on_id),
                dep_type=dep_type,
                created_by=created_by,
            )

        await add_event(
            issue.id,
            event_type="create",
            actor=created_by,
            old_value=None,
            new_value=issue.status,
            comment="Created",
        )

        # Timestamps are applied by the database on INSERT; reload so the
        # returned dict carries real values rather than None.
        await session.refresh(issue)
        return issue_to_dict(issue)


async def create_child_issue(
    parent_id: int,
    title: str = "",
    description: str = "",
    acceptance_criteria: str = "",
    notes: str = "",
    status: str = STATUS_OPEN,
    priority: int = DEFAULT_PRIORITY,
    issue_type: Literal["task", "subtask", "epic"] = TYPE_TASK,
    assignee: str | None = None,
    estimated_minutes: int | None = None,
    created_by: str = "",
    pinned: bool = False,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    """Create an issue and attach it beneath `parent_id`.

    The child gains a `parent-child` edge pointing at the parent. Creation and
    attachment share one transaction, so a failure to link never leaves an
    orphaned issue behind.
    """
    async with auto_session() as session:
        await _load_issue(session, parent_id)

        child = await create_issue(
            title=title,
            description=description,
            acceptance_criteria=acceptance_criteria,
            notes=notes,
            status=status,
            priority=priority,
            issue_type=issue_type,
            assignee=assignee,
            estimated_minutes=estimated_minutes,
            created_by=created_by,
            pinned=pinned,
            labels=labels,
        )

        await add_dependency(
            issue_id=child["id"],
            depends_on_id=parent_id,
            dep_type=DEP_PARENT_CHILD,
            created_by=created_by,
        )
        return child


async def create_epic_with_children(
    epic_kwargs: IssueKwargs,
    children_kwargs: list[IssueKwargs],
    *,
    epic_labels: list[str] | None = None,
    child_labels: list[str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Create an epic together with its child issues in a single transaction.

    The whole batch commits or none of it does, so a bad child definition
    cannot leave a half-populated epic that an agent would later mistake for a
    complete plan.

    Args:
        epic_kwargs: Fields for the epic. `issue_type` defaults to "epic".
        children_kwargs: One field bundle per child.
        epic_labels: Labels applied to the epic only.
        child_labels: Labels applied to every child.

    Returns:
        `(epic, [children...])` as JSON-safe dicts.
    """
    epic_params: dict[str, Any] = dict(epic_kwargs)
    # Only override the default; an explicit issue_type is respected.
    if epic_params.get("issue_type", TYPE_TASK) == TYPE_TASK:
        epic_params["issue_type"] = TYPE_EPIC

    async with auto_session():
        epic = await create_issue(**epic_params, labels=epic_labels)

        children: list[dict[str, Any]] = []
        for child_kwargs in children_kwargs:
            child = await create_child_issue(
                epic["id"], **child_kwargs, labels=child_labels
            )
            children.append(child)

        return epic, children


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


async def add_labels(issue_id: int, labels: Iterable[str]) -> list[str]:
    """Attach labels to an issue. Returns the labels that were applied."""
    label_list = normalize_labels(labels)

    async with auto_session() as session:
        await _load_issue(session, issue_id)
        for label in label_list:
            # merge() makes re-adding an existing label a no-op rather than a
            # primary key violation.
            await session.merge(Label(issue_id=issue_id, label=label))
        return label_list


async def remove_labels(issue_id: int, labels: Iterable[str]) -> int:
    """Detach labels from an issue. Returns how many rows were removed."""
    label_list = normalize_labels(labels)
    if not label_list:
        return 0

    async with auto_session() as session:
        await _load_issue(session, issue_id)
        rows = await session.execute(
            select(Label).where(Label.issue_id == issue_id, Label.label.in_(label_list))
        )
        matched = list(rows.scalars())
        for row in matched:
            await session.delete(row)
        return len(matched)


async def set_labels(issue_id: int, labels: Iterable[str]) -> list[str]:
    """Replace an issue's labels with exactly `labels`."""
    label_list = normalize_labels(labels)

    async with auto_session() as session:
        await _load_issue(session, issue_id)
        existing = await session.execute(
            select(Label).where(Label.issue_id == issue_id)
        )
        for row in existing.scalars():
            await session.delete(row)
        await session.flush()  # apply deletes before re-inserting

        for label in label_list:
            session.add(Label(issue_id=issue_id, label=label))
        return label_list


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


async def add_dependency(
    issue_id: int,
    depends_on_id: int,
    *,
    dep_type: str = DEP_BLOCKS,
    created_by: str = "",
    metadata: dict | None = None,
    thread_id: str = "",
) -> dict[str, Any]:
    """Create or update the edge `issue_id -> depends_on_id`.

    Re-adding an existing pair updates it in place; the pair is the primary
    key, so an issue relates to another in exactly one way at a time.

    Raises:
        ValidationError: Unknown `dep_type`, or an issue pointed at itself.
        IssueNotFoundError: Either endpoint is missing.
        DependencyCycleError: The edge would close a `blocks` or
            `parent-child` loop.
    """
    validate_dependency_type(dep_type)

    if issue_id == depends_on_id:
        raise ValidationError(f"issue {issue_id} cannot depend on itself.")

    async with auto_session() as session:
        await _load_issue(session, issue_id)
        await _load_issue(session, depends_on_id)
        await _guard_acyclic(session, issue_id, depends_on_id, dep_type)

        # The mapped attribute is `metadata_`; `metadata` is reserved by the
        # declarative base, and passing it as a keyword silently shadows the
        # class attribute instead of populating the column.
        edge = await session.merge(
            Dependency(
                issue_id=issue_id,
                depends_on_id=depends_on_id,
                type=dep_type,
                created_by=created_by,
                metadata_=metadata or {},
                thread_id=thread_id,
            )
        )

        await add_event(
            issue_id,
            event_type="dep.add",
            actor=created_by,
            old_value=None,
            new_value=f"{dep_type}:{depends_on_id}",
            comment="Added dependency",
        )
        return dependency_to_dict(edge)


async def remove_dependency(issue_id: int, depends_on_id: int) -> bool:
    """Delete the edge between two issues. Returns False if there was none."""
    async with auto_session() as session:
        edge = await session.get(
            Dependency, {"issue_id": issue_id, "depends_on_id": depends_on_id}
        )
        if edge is None:
            return False

        removed_type = edge.type
        await session.delete(edge)
        await add_event(
            issue_id,
            event_type="dep.remove",
            actor="",
            old_value=f"{removed_type}:{depends_on_id}",
            new_value=None,
            comment="Removed dependency",
        )
        return True


# ---------------------------------------------------------------------------
# Comments and events
# ---------------------------------------------------------------------------


async def add_comment(issue_id: int, author: str, text: str) -> dict[str, Any]:
    """Append a comment to an issue."""
    if not text or not text.strip():
        raise ValidationError("comment text is required and cannot be blank.")

    async with auto_session() as session:
        await _load_issue(session, issue_id)

        comment = Comment(
            issue_id=issue_id, author=author or "unknown", text=text.strip()
        )
        session.add(comment)
        await session.flush()

        await add_event(
            issue_id,
            event_type="comment.add",
            actor=author or "unknown",
            old_value=None,
            new_value=None,
            comment="Added comment",
        )

        await session.refresh(comment)
        return comment_to_dict(comment)


async def add_event(
    issue_id: int,
    *,
    event_type: str,
    actor: str,
    old_value: str | None,
    new_value: str | None,
    comment: str | None,
) -> dict[str, Any]:
    """Append an audit-trail entry to an issue's history.

    Verifies the issue exists first. Within a larger operation the row is
    already in the session's identity map, so this costs nothing; called on its
    own it turns a foreign-key violation into a message naming the bad id.
    """
    async with auto_session() as session:
        await _load_issue(session, issue_id)

        event = Event(
            issue_id=issue_id,
            event_type=event_type,
            actor=actor or "",
            old_value=old_value,
            new_value=new_value,
            comment=comment,
        )
        session.add(event)
        await session.flush()
        await session.refresh(event)
        return event_to_dict(event)


# ---------------------------------------------------------------------------
# Updates and lifecycle
# ---------------------------------------------------------------------------


async def update_issue_fields(
    issue_id: int,
    *,
    actor: str = "",
    status: str | None = None,
    priority: int | None = None,
    title: str | None = None,
    assignee: str | None = None,
    description: str | None = None,
    acceptance_criteria: str | None = None,
    notes: str | None = None,
    estimated_minutes: int | None = None,
) -> dict[str, Any]:
    """Apply a partial update, recording one event per field that changed.

    Only non-None arguments are considered, so callers send just what they
    want changed. Setting a field to its current value records nothing.

    Note:
        Because None means "leave alone", this cannot clear `assignee` or
        `estimated_minutes`. Use `unassign_issue` for the former.
    """
    if status is not None:
        validate_status(status)
    if priority is not None:
        validate_priority(priority)
    if title is not None:
        title = validate_title(title)
    if estimated_minutes is not None:
        validate_estimated_minutes(estimated_minutes)

    async with auto_session() as session:
        issue = await _load_issue(session, issue_id)

        changes = {
            "status": status,
            "priority": priority,
            "title": title,
            "assignee": assignee,
            "description": description,
            "acceptance_criteria": acceptance_criteria,
            "notes": notes,
            "estimated_minutes": estimated_minutes,
        }

        for field, new_value in changes.items():
            if new_value is None:
                continue
            old_value = getattr(issue, field)
            if new_value == old_value:
                continue

            setattr(issue, field, new_value)
            await add_event(
                issue_id,
                event_type=f"update.{field}",
                actor=actor,
                old_value=None if old_value is None else str(old_value),
                new_value=str(new_value),
                comment=f"Updated {field}",
            )

        await session.flush()
        # onupdate=func.now() expires updated_at; reload it before reading.
        await session.refresh(issue)
        return issue_to_dict(issue)


async def claim_issue(
    issue_id: int,
    *,
    actor: str,
    assignee: str,
    fail_if_claimed: bool = True,
) -> dict[str, Any]:
    """Assign an issue and move it to in_progress.

    Args:
        fail_if_claimed: When True, refuse if somebody else already holds it.
            This is the check that stops two agents working the same task.
    """
    if not assignee or not assignee.strip():
        raise ValidationError("assignee is required to claim an issue.")

    async with auto_session() as session:
        issue = await _load_issue(session, issue_id)

        if fail_if_claimed and issue.assignee and issue.assignee != assignee:
            raise ValidationError(
                f"issue {issue_id} is already claimed by {issue.assignee!r}; "
                f"pass fail_if_claimed=False to take it over."
            )

        return await update_issue_fields(
            issue_id, actor=actor, assignee=assignee, status=STATUS_IN_PROGRESS
        )


async def unassign_issue(issue_id: int, *, actor: str = "") -> dict[str, Any]:
    """Clear an issue's assignee, releasing it back to the pool."""
    async with auto_session() as session:
        issue = await _load_issue(session, issue_id)
        previous = issue.assignee

        if previous is None:
            return issue_to_dict(issue)

        issue.assignee = None
        await add_event(
            issue_id,
            event_type="update.assignee",
            actor=actor,
            old_value=previous,
            new_value=None,
            comment="Cleared assignee",
        )
        await session.flush()
        # onupdate=func.now() expires updated_at; reload it before reading.
        await session.refresh(issue)
        return issue_to_dict(issue)


async def close_issue(
    issue_id: int,
    *,
    actor: str,
    reason: str = "Closed",
    force: bool = False,
) -> dict[str, Any]:
    """Close an issue, recording `reason` on the audit event.

    Closing is idempotent: an already-closed issue is returned unchanged
    without a duplicate event.

    Args:
        force: Required to close a pinned issue.
    """
    async with auto_session() as session:
        issue = await _load_issue(session, issue_id)

        if issue.status == STATUS_CLOSED:
            return issue_to_dict(issue)

        if issue.pinned and not force:
            raise ValidationError(
                f"issue {issue_id} is pinned; pass force=True to close it."
            )

        old_status = issue.status
        issue.status = STATUS_CLOSED

        await add_event(
            issue_id,
            event_type="close",
            actor=actor,
            old_value=old_status,
            new_value=STATUS_CLOSED,
            comment=reason,
        )
        await session.flush()
        # onupdate=func.now() expires updated_at; reload it before reading.
        await session.refresh(issue)
        return issue_to_dict(issue)


async def reopen_issue(
    issue_id: int, *, actor: str = "", status: str = STATUS_OPEN
) -> dict[str, Any]:
    """Move a closed issue back into an active status."""
    if status == STATUS_CLOSED:
        raise ValidationError("reopen_issue cannot set status to 'closed'.")
    validate_status(status)

    async with auto_session() as session:
        issue = await _load_issue(session, issue_id)

        if issue.status != STATUS_CLOSED:
            return issue_to_dict(issue)

        issue.status = status
        await add_event(
            issue_id,
            event_type="reopen",
            actor=actor,
            old_value=STATUS_CLOSED,
            new_value=status,
            comment="Reopened",
        )
        await session.flush()
        # onupdate=func.now() expires updated_at; reload it before reading.
        await session.refresh(issue)
        return issue_to_dict(issue)


async def delete_issue(issue_id: int) -> bool:
    """Permanently delete an issue and everything attached to it.

    Labels, comments, events and edges in both directions go with it via
    cascade. Prefer `close_issue`: closing preserves the history that makes
    this server useful as a memory.
    """
    async with auto_session() as session:
        issue = await session.get(Issue, issue_id)
        if issue is None:
            return False
        await session.delete(issue)
        return True
