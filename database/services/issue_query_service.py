"""Read operations over the issue graph.

The write side keeps the graph consistent; this side answers the questions an
agent actually asks when it resumes work:

* `get_issue_details` - everything about one issue.
* `list_issues`       - filtered, paginated browsing.
* `get_ready_work`    - what can be started right now.
* `get_blocked_issues`- what is stuck, and on what.
* `get_issue_tree`    - an epic and its descendants.
* `get_issue_stats`   - a one-call overview of the whole board.
* `find_cycles`       - diagnostic for pre-existing bad data.

`get_ready_work` is the important one. Without it an agent must pull every
issue and reason about dependencies itself, which is exactly the context-window
pressure this server exists to relieve.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from sqlalchemy import Select, func, or_, select

from ..db_client import auto_session
from ..domain import (
    ACTIVE_STATUSES,
    BLOCKING_DEPENDENCY_TYPES,
    DEP_PARENT_CHILD,
    STATUS_CLOSED,
    STATUS_OPEN,
    TYPE_EPIC,
    ValidationError,
    validate_status,
)
from ..models import Comment, Dependency, Issue, Label
from ..serializers import comment_to_dict, issue_summary, issue_to_dict

__all__ = [
    "get_issue_details",
    "list_issues",
    "get_ready_work",
    "get_blocked_issues",
    "get_issue_tree",
    "get_issue_stats",
    "find_cycles",
]

DEFAULT_LIMIT = 50
MAX_LIMIT = 500


def _clamp_limit(limit: int) -> int:
    """Keep result sets bounded so one call cannot flood an agent's context."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValidationError(f"limit must be a positive integer, got {limit!r}.")
    return min(limit, MAX_LIMIT)


def _blocked_issue_ids() -> Select:
    """Subquery: ids of issues held up by at least one unfinished blocker."""
    blocker = Issue.__table__.alias("blocker")
    return (
        select(Dependency.issue_id)
        .join(blocker, Dependency.depends_on_id == blocker.c.id)
        .where(
            Dependency.type.in_(BLOCKING_DEPENDENCY_TYPES),
            blocker.c.status != STATUS_CLOSED,
        )
    )


async def _labels_for(session, issue_ids: Sequence[int]) -> dict[int, list[str]]:
    """Fetch labels for many issues in one query, keyed by issue id."""
    if not issue_ids:
        return {}
    rows = await session.execute(
        select(Label.issue_id, Label.label).where(Label.issue_id.in_(issue_ids))
    )
    grouped: dict[int, list[str]] = {}
    for issue_id, label in rows.all():
        grouped.setdefault(issue_id, []).append(label)
    return grouped


# ---------------------------------------------------------------------------
# Single issue
# ---------------------------------------------------------------------------


async def get_issue_details(
    issue_id: int, include_nested_deps: bool = True
) -> dict[str, Any]:
    """Return one issue with its labels, comments, edges and parent.

    Args:
        issue_id: The issue to describe.
        include_nested_deps: Also report each neighbour's own edges, giving one
            more hop of graph context without a second round trip.

    Returns:
        Issue fields plus `labels`, `comments`, `dependencies`, `dependents`,
        `parent`, and `is_blocked`.

    Raises:
        ValueError: No issue has that id.
    """
    async with auto_session() as session:
        issue = await session.get(Issue, issue_id)
        if issue is None:
            raise ValueError(f"issue not found: {issue_id}")

        labels = list(
            (
                await session.execute(
                    select(Label.label).where(Label.issue_id == issue_id)
                )
            ).scalars()
        )

        comments = list(
            (
                await session.execute(
                    select(Comment)
                    .where(Comment.issue_id == issue_id)
                    .order_by(Comment.created_at, Comment.id)
                )
            ).scalars()
        )

        outgoing = list(
            (
                await session.execute(
                    select(Dependency).where(Dependency.issue_id == issue_id)
                )
            ).scalars()
        )
        incoming = list(
            (
                await session.execute(
                    select(Dependency).where(Dependency.depends_on_id == issue_id)
                )
            ).scalars()
        )

        neighbour_ids = {edge.depends_on_id for edge in outgoing} | {
            edge.issue_id for edge in incoming
        }
        neighbours: dict[int, Issue] = {}
        if neighbour_ids:
            rows = await session.execute(
                select(Issue).where(Issue.id.in_(neighbour_ids))
            )
            neighbours = {row.id: row for row in rows.scalars()}

        nested: dict[int, dict[str, Any]] = {}
        if include_nested_deps and neighbour_ids:
            nested = await _nested_edges(session, neighbour_ids)

        def describe(edge: Dependency, other_id: int) -> dict[str, Any] | None:
            other = neighbours.get(other_id)
            if other is None:
                return None
            entry = {**issue_summary(other), "dependency_type": edge.type}
            if other_id in nested:
                entry.update(nested[other_id])
            return entry

        dependencies = [
            entry
            for entry in (describe(e, e.depends_on_id) for e in outgoing)
            if entry is not None
        ]
        dependents = [
            entry
            for entry in (describe(e, e.issue_id) for e in incoming)
            if entry is not None
        ]

        parent = next(
            (
                edge.depends_on_id
                for edge in sorted(outgoing, key=lambda e: e.depends_on_id)
                if edge.type == DEP_PARENT_CHILD
            ),
            None,
        )

        is_blocked = any(
            edge.type in BLOCKING_DEPENDENCY_TYPES
            and (blocker := neighbours.get(edge.depends_on_id)) is not None
            and blocker.status != STATUS_CLOSED
            for edge in outgoing
        )

        return {
            **issue_to_dict(issue),
            "labels": labels,
            "comments": [comment_to_dict(c) for c in comments],
            "dependencies": dependencies,
            "dependents": dependents,
            "parent": parent,
            "is_blocked": is_blocked,
        }


async def _nested_edges(session, issue_ids: Iterable[int]) -> dict[int, dict[str, Any]]:
    """Return one further hop of edges for each of `issue_ids`."""
    ids = list(issue_ids)
    outgoing = list(
        (
            await session.execute(
                select(Dependency).where(Dependency.issue_id.in_(ids))
            )
        ).scalars()
    )
    incoming = list(
        (
            await session.execute(
                select(Dependency).where(Dependency.depends_on_id.in_(ids))
            )
        ).scalars()
    )

    referenced = {e.depends_on_id for e in outgoing} | {e.issue_id for e in incoming}
    titles: dict[int, str] = {}
    if referenced:
        rows = await session.execute(
            select(Issue.id, Issue.title).where(Issue.id.in_(referenced))
        )
        titles = dict(rows.all())

    result: dict[int, dict[str, Any]] = {}
    for issue_id in ids:
        result[issue_id] = {
            "dependencies": [
                {
                    "id": e.depends_on_id,
                    "title": titles.get(e.depends_on_id),
                    "dependency_type": e.type,
                }
                for e in outgoing
                if e.issue_id == issue_id
            ],
            "dependents": [
                {
                    "id": e.issue_id,
                    "title": titles.get(e.issue_id),
                    "dependency_type": e.type,
                }
                for e in incoming
                if e.depends_on_id == issue_id
            ],
        }
    return result


# ---------------------------------------------------------------------------
# Browsing
# ---------------------------------------------------------------------------


async def list_issues(
    *,
    status: str | list[str] | None = None,
    issue_type: str | None = None,
    assignee: str | None = None,
    priority_max: int | None = None,
    labels: list[str] | None = None,
    search: str | None = None,
    include_closed: bool = False,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """List issues matching every supplied filter.

    Args:
        status: One status or several; overrides `include_closed`.
        priority_max: Keep issues at least this urgent (numerically <=).
        labels: Keep issues carrying *all* of these labels.
        search: Case-insensitive substring match on title and description.
        include_closed: Ignored when `status` is given.
        limit: Capped at 500.

    Returns:
        `{"total": int, "count": int, "limit": int, "offset": int,
          "issues": [...]}` where `total` is the unpaginated match count, so a
        caller can tell a full page from the end of the results.
    """
    limit = _clamp_limit(limit)
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValidationError(f"offset must be a non-negative integer, got {offset!r}.")

    filters = []

    if status is not None:
        wanted = [status] if isinstance(status, str) else list(status)
        for value in wanted:
            validate_status(value)
        filters.append(Issue.status.in_(wanted))
    elif not include_closed:
        filters.append(Issue.status.in_(ACTIVE_STATUSES))

    if issue_type is not None:
        filters.append(Issue.issue_type == issue_type)
    if assignee is not None:
        filters.append(Issue.assignee == assignee)
    if priority_max is not None:
        filters.append(Issue.priority <= priority_max)

    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(Issue.title.ilike(pattern), Issue.description.ilike(pattern))
        )

    if labels:
        # Require every label: count the matching label rows per issue and
        # keep only issues whose count equals the number requested.
        wanted_labels = [label.strip() for label in labels if label.strip()]
        if wanted_labels:
            matching = (
                select(Label.issue_id)
                .where(Label.label.in_(wanted_labels))
                .group_by(Label.issue_id)
                .having(func.count(func.distinct(Label.label)) == len(wanted_labels))
            )
            filters.append(Issue.id.in_(matching))

    async with auto_session() as session:
        total = await session.scalar(
            select(func.count()).select_from(Issue).where(*filters)
        )

        rows = await session.execute(
            select(Issue)
            .where(*filters)
            .order_by(Issue.pinned.desc(), Issue.priority.asc(), Issue.id.asc())
            .limit(limit)
            .offset(offset)
        )
        issues = list(rows.scalars())
        label_map = await _labels_for(session, [i.id for i in issues])

        return {
            "total": int(total or 0),
            "count": len(issues),
            "limit": limit,
            "offset": offset,
            "issues": [
                {**issue_summary(i), "labels": label_map.get(i.id, [])} for i in issues
            ],
        }


# ---------------------------------------------------------------------------
# Execution planning
# ---------------------------------------------------------------------------


async def get_ready_work(
    *,
    assignee: str | None = None,
    limit: int = DEFAULT_LIMIT,
    include_epics: bool = False,
) -> dict[str, Any]:
    """Return open issues with nothing left blocking them.

    An issue is ready when its status is `open` and every issue it depends on
    through a `blocks` edge is closed. `parent-child` is containment rather
    than sequencing, so belonging to an unfinished epic does not make a task
    unready.

    Args:
        assignee: Restrict to one person's queue. Pass nothing for the shared
            pool.
        include_epics: Epics are excluded by default; they are containers, and
            an agent told to "start" one has nothing concrete to do.

    Returns:
        `{"count": int, "issues": [...]}` ordered by pinned, then priority,
        then id, so the first entry is the best next task.
    """
    limit = _clamp_limit(limit)

    filters = [Issue.status == STATUS_OPEN, Issue.id.not_in(_blocked_issue_ids())]
    if not include_epics:
        filters.append(Issue.issue_type != TYPE_EPIC)
    if assignee is not None:
        filters.append(Issue.assignee == assignee)

    async with auto_session() as session:
        rows = await session.execute(
            select(Issue)
            .where(*filters)
            .order_by(Issue.pinned.desc(), Issue.priority.asc(), Issue.id.asc())
            .limit(limit)
        )
        issues = list(rows.scalars())
        label_map = await _labels_for(session, [i.id for i in issues])

        return {
            "count": len(issues),
            "issues": [
                {**issue_summary(i), "labels": label_map.get(i.id, [])} for i in issues
            ],
        }


async def get_blocked_issues(*, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """Return unfinished issues that are waiting on something, and on what.

    Each entry carries a `blocked_by` list naming the unfinished blockers, so
    the answer to "why is this stuck?" needs no follow-up call.
    """
    limit = _clamp_limit(limit)

    async with auto_session() as session:
        rows = await session.execute(
            select(Issue)
            .where(
                Issue.status.in_(ACTIVE_STATUSES),
                Issue.id.in_(_blocked_issue_ids()),
            )
            .order_by(Issue.priority.asc(), Issue.id.asc())
            .limit(limit)
        )
        issues = list(rows.scalars())
        if not issues:
            return {"count": 0, "issues": []}

        issue_ids = [i.id for i in issues]
        blocker_rows = await session.execute(
            select(Dependency.issue_id, Issue)
            .join(Issue, Dependency.depends_on_id == Issue.id)
            .where(
                Dependency.issue_id.in_(issue_ids),
                Dependency.type.in_(BLOCKING_DEPENDENCY_TYPES),
                Issue.status != STATUS_CLOSED,
            )
        )
        blockers: dict[int, list[dict[str, Any]]] = {}
        for blocked_id, blocker in blocker_rows.all():
            blockers.setdefault(blocked_id, []).append(issue_summary(blocker))

        return {
            "count": len(issues),
            "issues": [
                {**issue_summary(i), "blocked_by": blockers.get(i.id, [])}
                for i in issues
            ],
        }


# ---------------------------------------------------------------------------
# Hierarchy
# ---------------------------------------------------------------------------


async def get_issue_tree(root_id: int, *, max_depth: int = 5) -> dict[str, Any]:
    """Return an issue and its descendants through `parent-child` edges.

    Args:
        max_depth: How many levels below the root to walk, bounding the
            response for deep hierarchies.

    Returns:
        The root summary with a nested `children` list and a `descendant_count`
        of everything returned beneath it.
    """
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth < 0:
        raise ValidationError(
            f"max_depth must be a non-negative integer, got {max_depth!r}."
        )

    async with auto_session() as session:
        root = await session.get(Issue, root_id)
        if root is None:
            raise ValueError(f"issue not found: {root_id}")

        # Walk level by level so the whole tree costs one query per depth
        # rather than one per node.
        levels: list[dict[int, list[Issue]]] = []
        frontier = [root_id]
        seen = {root_id}

        for _ in range(max_depth):
            if not frontier:
                break
            rows = await session.execute(
                select(Dependency.depends_on_id, Issue)
                .join(Issue, Dependency.issue_id == Issue.id)
                .where(
                    Dependency.depends_on_id.in_(frontier),
                    Dependency.type == DEP_PARENT_CHILD,
                )
                .order_by(Issue.priority.asc(), Issue.id.asc())
            )
            by_parent: dict[int, list[Issue]] = {}
            next_frontier = []
            for parent_id, child in rows.all():
                if child.id in seen:  # guard against malformed cyclic data
                    continue
                seen.add(child.id)
                by_parent.setdefault(parent_id, []).append(child)
                next_frontier.append(child.id)

            if not by_parent:
                break
            levels.append(by_parent)
            frontier = next_frontier

        def build(issue: Issue, depth: int) -> dict[str, Any]:
            node = issue_summary(issue)
            children = levels[depth].get(issue.id, []) if depth < len(levels) else []
            node["children"] = [build(child, depth + 1) for child in children]
            return node

        tree = build(root, 0)
        tree["descendant_count"] = len(seen) - 1
        return tree


# ---------------------------------------------------------------------------
# Overview and diagnostics
# ---------------------------------------------------------------------------


async def get_issue_stats() -> dict[str, Any]:
    """Return board-wide counts: by status, type and priority, plus totals.

    Cheap enough to call at the start of a session to re-establish context in
    one round trip.
    """
    async with auto_session() as session:
        status_rows = await session.execute(
            select(Issue.status, func.count()).group_by(Issue.status)
        )
        by_status = {status: count for status, count in status_rows.all()}

        type_rows = await session.execute(
            select(Issue.issue_type, func.count()).group_by(Issue.issue_type)
        )
        by_type = {kind: count for kind, count in type_rows.all()}

        priority_rows = await session.execute(
            select(Issue.priority, func.count()).group_by(Issue.priority)
        )
        by_priority = {f"P{p}": count for p, count in priority_rows.all()}

        ready = await session.scalar(
            select(func.count())
            .select_from(Issue)
            .where(
                Issue.status == STATUS_OPEN,
                Issue.issue_type != TYPE_EPIC,
                Issue.id.not_in(_blocked_issue_ids()),
            )
        )
        blocked = await session.scalar(
            select(func.count())
            .select_from(Issue)
            .where(
                Issue.status.in_(ACTIVE_STATUSES),
                Issue.id.in_(_blocked_issue_ids()),
            )
        )
        total = await session.scalar(select(func.count()).select_from(Issue))

        return {
            "total": int(total or 0),
            "open": int(by_status.get(STATUS_OPEN, 0)),
            "closed": int(by_status.get(STATUS_CLOSED, 0)),
            "ready": int(ready or 0),
            "blocked": int(blocked or 0),
            "by_status": by_status,
            "by_type": by_type,
            "by_priority": by_priority,
        }


async def find_cycles(*, dep_type: str = "blocks") -> dict[str, Any]:
    """Detect dependency cycles already present in the data.

    New edges are refused if they would close a loop, but a database written
    by an older version, or by hand, can still contain one. A `blocks` cycle
    makes every issue in it permanently unready, which otherwise shows up only
    as work mysteriously absent from `get_ready_work`.

    Returns:
        `{"dep_type": str, "count": int, "cycles": [[id, ...], ...]}` with each
        cycle listed once, rotated to start at its smallest id.
    """
    async with auto_session() as session:
        rows = await session.execute(
            select(Dependency.issue_id, Dependency.depends_on_id).where(
                Dependency.type == dep_type
            )
        )
        edges: dict[int, list[int]] = {}
        for source, target in rows.all():
            edges.setdefault(source, []).append(target)

        found: set[tuple[int, ...]] = set()
        colour: dict[int, int] = {}  # 1 = on current path, 2 = finished

        def visit(node: int, path: list[int]) -> None:
            colour[node] = 1
            path.append(node)
            for neighbour in edges.get(node, []):
                if colour.get(neighbour) == 1:
                    cycle = path[path.index(neighbour) :]
                    pivot = cycle.index(min(cycle))
                    found.add(tuple(cycle[pivot:] + cycle[:pivot]))
                elif colour.get(neighbour) is None:
                    visit(neighbour, path)
            path.pop()
            colour[node] = 2

        for node in list(edges):
            if colour.get(node) is None:
                visit(node, [])

        cycles = sorted(list(cycle) for cycle in found)
        return {"dep_type": dep_type, "count": len(cycles), "cycles": cycles}
