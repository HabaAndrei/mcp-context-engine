"""Service functions to create/update/close issues in a Beads-compatible SQLite DB.

These helpers mirror the *current* Beads behaviors conceptually:
- Create issue with many optional fields
- Create child issue (parent-child edge)
- Add labels
- Add dependencies (blocks/related/parent-child/etc.)
- Add comments
- Update common issue fields (status, priority, title, description, design, notes, acceptance_criteria, assignee, external_ref, estimated_minutes)
- Claim issue (similar to `bd update <id> --claim` concept: set assignee and status to in_progress)
- Close issue with reason (records an Event row; stores closure metadata)

Notes:
- This is a Python-side API. It does NOT attempt to replicate every Go-side invariant.
- Beads represents hierarchy using Dependency edges: child -> parent with type='parent-child'.
- All functions are async and use the global session from get_session().
"""

from __future__ import annotations

from typing import Iterable, Literal, TypedDict

from sqlalchemy import select

from ..db_client import auto_session
from ..models import Comment, Dependency, Event, Issue, Label


# -------------------------
# Common constants (Beads-like)
# -------------------------

STATUS_OPEN = "open"
STATUS_IN_PROGRESS = "in_progress"
STATUS_BLOCKED = "blocked"
STATUS_DEFERRED = "deferred"
STATUS_CLOSED = "closed"

DEP_BLOCKS = "blocks"
DEP_PARENT_CHILD = "parent-child"
DEP_RELATED = "related"
DEP_DUPLICATES = "duplicates"
DEP_SUPERSEDES = "supersedes"


class IssueKwargs(TypedDict, total=False):
    """Type hint for issue creation parameters.

    All fields are optional. Use this for type hints when passing
    issue parameters as a dictionary (e.g., in create_epic_with_children).
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


# -------------------------
# Create
# -------------------------


async def create_issue(
    title: str = "",
    description: str = "",
    acceptance_criteria: str = "",
    notes: str = "",
    status: str = STATUS_OPEN,
    priority: int = 2,
    issue_type: Literal["task", "subtask", "epic"] = "task",
    assignee: str | None = None,
    estimated_minutes: int | None = None,
    created_by: str = "",
    pinned: bool = False,
    labels: list[str] | None = None,
    dependencies: list | None = None,
) -> dict:
    """Create an issue with optional labels and dependency edges.

    Args:
        params: CreateIssueParams
        labels: list of label strings (optional)
        dependencies: list of (depends_on_id, dep_type) edges where this new issue is the source

    Returns:
        The created Issue (attached to session with auto-generated integer ID).

    Notes:
        - Issue ID is auto-generated as an auto-incrementing integer.
        - created_at and updated_at are automatically set by the database.
    """
    async with auto_session() as session:
        if not title:
            raise ValueError("title is required")

        issue = Issue(
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
        )

        session.add(issue)
        await session.flush()  # Flush to get the auto-generated ID

        if labels:
            await add_labels(issue.id, labels)

        if dependencies:
            for depends_on_id, dep_type in dependencies:
                await add_dependency(issue.id, depends_on_id, dep_type=dep_type, created_by=created_by)

        # small, useful event
        await add_event(
            issue.id,
            event_type="create",
            actor=created_by or "",
            old_value=None,
            new_value=issue.status,
            comment="Created",
        )

        return issue.__dict__


async def create_child_issue(
    parent_id: int,
    title: str = "",
    description: str = "",
    acceptance_criteria: str = "",
    notes: str = "",
    status: str = STATUS_OPEN,
    priority: int = 2,
    issue_type: Literal["task", "subtask", "epic"] = "task",
    assignee: str | None = None,
    estimated_minutes: int | None = None,
    created_by: str = "",
    pinned: bool = False,
    labels: list[str] | None = None,
) -> dict:
    """Create an issue as a child of another issue.

    Implements Beads hierarchy convention:
      child --(parent-child)--> parent
    """
    async with auto_session() as session:
        # ensure parent exists
        parent = await session.get(Issue, parent_id)
        if parent is None:
            raise ValueError(f"parent issue not found: {parent_id}")

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
) -> tuple[dict, list[dict]]:
    """Create an epic and N child issues under it.

    This is a convenience wrapper for the common "epic + tasks" workflow.

    Args:
        epic_kwargs: Dictionary of kwargs for the epic issue (see IssueKwargs for available fields)
        children_kwargs: List of dictionaries of kwargs for child issues (see IssueKwargs for available fields)
        epic_labels: Optional labels for the epic
        child_labels: Optional labels for all children

    Returns:
        Tuple of (epic_issue, list of child issues)

    Example:
        epic, children = await create_epic_with_children(
            epic_kwargs={"title": "Build Auth System", "priority": 1},
            children_kwargs=[
                {"title": "Login Page", "description": "Create login UI"},
                {"title": "JWT Tokens", "description": "Implement token generation"},
            ],
            epic_labels=["backend"],
            child_labels=["auth"]
        )
    """

    # Ensure epic has issue_type set to "epic"
    epic_params = {**epic_kwargs}
    if epic_params.get("issue_type", "task") == "task":
        epic_params["issue_type"] = "epic"

    epic_issue = await create_issue(**epic_params, labels=epic_labels)

    created_children: list[dict] = []
    for child_kwargs in children_kwargs:
        child = await create_child_issue(epic_issue["id"], **child_kwargs, labels=child_labels)
        created_children.append(child)

    return epic_issue, created_children


# -------------------------
# Labels
# -------------------------


async def add_labels(issue_id: int, labels: Iterable[str]) -> str:
    # Validate that labels is not a string (common mistake)
    if isinstance(labels, str):
        raise TypeError(
            "labels must be a list of strings, not a single string. "
            f"Use add_labels({issue_id}, ['your_label']) instead of add_labels({issue_id}, 'your_label')"
        )

    async with auto_session() as session:
        for label in labels:
            label = label.strip()
            if not label:
                continue
            await session.merge(Label(issue_id=issue_id, label=label))
    return "Success!"


async def remove_labels(issue_id: int, labels: Iterable[str]) -> int:
    """Remove labels from an issue. Returns number removed."""
    # Validate that labels is not a string (common mistake)
    if isinstance(labels, str):
        raise TypeError(
            "labels must be a list of strings, not a single string. "
            f"Use remove_labels({issue_id}, ['your_label']) instead of remove_labels({issue_id}, 'your_label')"
        )

    async with auto_session() as session:
        labels = [i.strip() for i in labels if i.strip()]
        if not labels:
            return 0

        q = select(Label).where(Label.issue_id == issue_id, Label.label.in_(labels))
        result = await session.execute(q)
        rows = list(result.scalars())
        for r in rows:
            await session.delete(r)
        return len(rows)


async def set_labels(issue_id: int, labels: Iterable[str]) -> None:
    """Replace all labels on an issue."""
    # Validate that labels is not a string (common mistake)
    if isinstance(labels, str):
        raise TypeError(
            "labels must be a list of strings, not a single string. "
            f"Use set_labels({issue_id}, ['your_label']) instead of set_labels({issue_id}, 'your_label')"
        )

    async with auto_session() as session:
        # delete existing
        q = select(Label).where(Label.issue_id == issue_id)
        result = await session.execute(q)
        for r in result.scalars():
            await session.delete(r)

        await add_labels(issue_id, labels)


# -------------------------
# Dependencies
# -------------------------


async def add_dependency(
    issue_id: int,
    depends_on_id: int,
    *,
    dep_type: str = DEP_BLOCKS,
    created_by: str = "",
    metadata: dict | None = None,
    thread_id: str = "",
) -> dict:
    """Create or upsert a dependency edge."""
    async with auto_session() as session:
        if await session.get(Issue, issue_id) is None:
            raise ValueError(f"issue not found: {issue_id}")
        if await session.get(Issue, depends_on_id) is None:
            raise ValueError(f"depends_on issue not found: {depends_on_id}")

        dep = Dependency(
            issue_id=issue_id,
            depends_on_id=depends_on_id,
            type=dep_type,
            created_by=created_by,
            metadata=metadata or {},
            thread_id=thread_id,
        )

        await session.merge(dep)

        await add_event(
            issue_id,
            event_type="dep.add",
            actor=created_by,
            old_value=None,
            new_value=f"{dep_type}:{depends_on_id}",
            comment="Added dependency",
        )

        return dep.__dict__


async def remove_dependency(issue_id: int, depends_on_id: int) -> bool:
    async with auto_session() as session:
        dep = await session.get(Dependency, {"issue_id": issue_id, "depends_on_id": depends_on_id})
        if dep is None:
            return False
        await session.delete(dep)
        return True


# -------------------------
# Comments
# -------------------------


async def add_comment(issue_id: int, author: str, text: str) -> dict:
    async with auto_session() as session:
        if not author:
            author = "unknown"
        if not text:
            raise ValueError("comment text required")

        if await session.get(Issue, issue_id) is None:
            raise ValueError(f"issue not found: {issue_id}")

        c = Comment(issue_id=issue_id, author=author, text=text)
        session.add(c)

        await add_event(
            issue_id,
            event_type="comment.add",
            actor=author,
            old_value=None,
            new_value=None,
            comment="Added comment",
        )

        return c.__dict__


# -------------------------
# Update / Claim / Close
# -------------------------


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
) -> dict:
    """Update common Issue fields (Beads-like `bd update`)."""
    async with auto_session() as session:
        issue = await session.get(Issue, issue_id)
        if issue is None:
            raise ValueError(f"issue not found: {issue_id}")

        async def set_field(field: str, new_value):
            old_value = getattr(issue, field)
            if new_value is None or new_value == old_value:
                return
            setattr(issue, field, new_value)
            await add_event(
                issue_id,
                event_type=f"update.{field}",
                actor=actor,
                old_value=str(old_value) if old_value is not None else None,
                new_value=str(new_value) if new_value is not None else None,
                comment=f"Updated {field}",
            )

        await set_field("status", status)
        await set_field("priority", priority)
        await set_field("title", title)
        await set_field("assignee", assignee)
        await set_field("description", description)
        await set_field("acceptance_criteria", acceptance_criteria)
        await set_field("notes", notes)
        await set_field("estimated_minutes", estimated_minutes)

        return issue.__dict__


async def claim_issue(
    issue_id: int,
    *,
    actor: str,
    assignee: str,
    fail_if_claimed: bool = True,
) -> dict:
    """Claim issue (roughly analogous to `bd update <id> --claim`).

    Behavior:
    - If already assigned and fail_if_claimed=True -> raises
    - Sets assignee
    - Sets status to in_progress
    - Records events
    """
    async with auto_session() as session:
        issue = await session.get(Issue, issue_id)
        if issue is None:
            raise ValueError(f"issue not found: {issue_id}")

        if fail_if_claimed and issue.assignee and issue.assignee != assignee:
            raise ValueError(f"issue already claimed by {issue.assignee}")

        return await update_issue_fields(issue_id, actor=actor, assignee=assignee, status=STATUS_IN_PROGRESS)


async def close_issue(
    issue_id: int,
    *,
    actor: str,
    reason: str = "Closed",
    force: bool = False,
) -> dict:
    """Close an issue.

    Notes:
    - Beads has extra checks (pinned/template); we expose force flag but don't enforce those rules here.
    - We also write an Event row with reason.
    """
    async with auto_session() as session:
        issue = await session.get(Issue, issue_id)
        if issue is None:
            raise ValueError(f"issue not found: {issue_id}")

        if issue.status == STATUS_CLOSED:
            return issue

        # (optional) checks; if you want stricter Beads rules you can extend these.
        if not force and getattr(issue, "pinned", False):
            raise ValueError("cannot close pinned issue without force=True")

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

        return issue.__dict__


# -------------------------
# Events
# -------------------------


async def add_event(
    issue_id: int,
    *,
    event_type: str,
    actor: str,
    old_value: str | None,
    new_value: str | None,
    comment: str | None,
) -> dict:
    async with auto_session() as session:
        e = Event(
            issue_id=issue_id,
            event_type=event_type,
            actor=actor or "",
            old_value=old_value,
            new_value=new_value,
            comment=comment,
        )
        session.add(e)
        return e.__dict__
