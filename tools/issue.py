"""Issue lifecycle MCP tools.

Note on what is deliberately absent: `database.services.delete_issue` exists
but is not exposed as a tool. Deletion is unrecoverable and takes the issue's
comments and audit trail with it - the very record this server exists to keep.
Closing an issue conveys the same "this is done" meaning while preserving the
history, so closing is what the tool surface offers. Operators who genuinely
need deletion can call the service function directly.
"""

from typing import Literal

from mcp_engine import mcp

from database.services import (
    STATUS_OPEN,
    IssueKwargs,
    claim_issue,
    close_issue,
    create_child_issue,
    create_epic_with_children,
    create_issue,
    reopen_issue,
    unassign_issue,
    update_issue_fields,
)

from ._common import failure


@mcp.tool()
async def con_mcp_create_issue(
    title: str,
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
):
    """Create an issue.

    Args:
        title: Short summary (REQUIRED, non-blank, max 500 characters).
        description: The full explanation.
        acceptance_criteria: What "done" means for this issue.
        notes: Anything else worth keeping.
        status: "open" (default), "in_progress", "blocked", "deferred", "closed".
        priority: 0-4, where 0 is most urgent (default 2).
        issue_type: "task" (default), "subtask" or "epic".
        assignee: Who owns it.
        estimated_minutes: Time estimate, non-negative.
        created_by: Who is creating it.
        pinned: Pin to the top of listings; pinned issues need force to close.
        labels: Tags, e.g. ["backend", "bug"].
        dependencies: Pairs of [issue_id, dep_type] with this new issue as the
            source, e.g. [[12, "blocks"]]. Use nested lists, not tuples, so the
            value survives JSON.

    Returns:
        The created issue including its assigned id, or an error message.
    """
    try:
        return await create_issue(
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
            dependencies=dependencies,
        )
    except Exception as exc:
        return failure(f"creating issue {title!r}", exc)


@mcp.tool()
async def con_mcp_create_child_issue(
    parent_id: int,
    title: str,
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
):
    """Create an issue nested under an existing one.

    Adds the parent-child edge automatically. Being inside an unfinished parent
    does not block the child - use a "blocks" dependency for ordering.

    Args:
        parent_id: The issue to nest under (REQUIRED, must exist).
        title: Short summary (REQUIRED).
        (remaining arguments behave as in con_mcp_create_issue)

    Returns:
        The created child issue, or an error message if the parent is missing.
    """
    try:
        return await create_child_issue(
            parent_id=parent_id,
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
    except Exception as exc:
        return failure(f"creating child issue {title!r} under {parent_id}", exc)


@mcp.tool()
async def con_mcp_create_epic_with_children(
    epic_kwargs: IssueKwargs,
    children_kwargs: list[IssueKwargs],
    epic_labels: list[str] | None = None,
    child_labels: list[str] | None = None,
):
    """Create an epic and all its child tasks in one atomic operation.

    The whole batch commits together, so a bad child definition cannot leave a
    half-built epic that looks like a finished plan. This is the efficient way
    to record a breakdown you have just worked out.

    Args:
        epic_kwargs: Fields for the epic, e.g. {"title": "Auth", "priority": 1}.
            issue_type defaults to "epic".
        children_kwargs: One dict per child, e.g. [{"title": "Login page"}].
        epic_labels: Labels for the epic only.
        child_labels: Labels applied to every child.

    Returns:
        {"epic": {...}, "children": [...]} or an error message.

    Example:
        con_mcp_create_epic_with_children(
            epic_kwargs={"title": "Build auth", "priority": 1},
            children_kwargs=[{"title": "Login"}, {"title": "Tokens"}],
            child_labels=["auth"],
        )
    """
    try:
        epic, children = await create_epic_with_children(
            epic_kwargs=epic_kwargs,
            children_kwargs=children_kwargs,
            epic_labels=epic_labels,
            child_labels=child_labels,
        )
        return {"epic": epic, "children": children}
    except Exception as exc:
        return failure("creating epic with children", exc)


@mcp.tool()
async def con_mcp_update_issue_fields(
    issue_id: int,
    actor: str = "",
    status: str | None = None,
    priority: int | None = None,
    title: str | None = None,
    assignee: str | None = None,
    description: str | None = None,
    acceptance_criteria: str | None = None,
    notes: str | None = None,
    estimated_minutes: int | None = None,
):
    """Update selected fields of an issue.

    Send only what should change; omitted fields are left alone. Each field
    that actually changes is recorded in the issue's audit trail.

    Because omission means "leave alone", this cannot clear a field. Use
    con_mcp_unassign_issue to remove an assignee.

    Args:
        issue_id: Issue to update (REQUIRED).
        actor: Who is making the change, recorded on each event.
        status: "open", "in_progress", "blocked", "deferred", "closed".
        priority: 0-4, where 0 is most urgent.
        title: New summary, max 500 characters.
        assignee: New owner.
        description, acceptance_criteria, notes: Replacement text.
        estimated_minutes: New estimate, non-negative.

    Returns:
        The updated issue, or an error message.
    """
    try:
        return await update_issue_fields(
            issue_id=issue_id,
            actor=actor,
            status=status,
            priority=priority,
            title=title,
            assignee=assignee,
            description=description,
            acceptance_criteria=acceptance_criteria,
            notes=notes,
            estimated_minutes=estimated_minutes,
        )
    except Exception as exc:
        return failure(f"updating issue {issue_id}", exc)


@mcp.tool()
async def con_mcp_claim_issue(
    issue_id: int,
    actor: str,
    assignee: str,
    fail_if_claimed: bool = True,
):
    """Take ownership of an issue and mark it in progress.

    Claim before starting work. With several agents on one board, the
    fail_if_claimed check is what stops two of them doing the same task.

    Args:
        issue_id: Issue to claim (REQUIRED).
        actor: Who is performing the claim (REQUIRED).
        assignee: Who the issue is being assigned to (REQUIRED).
        fail_if_claimed: Refuse if somebody else already holds it (default
            True). Pass False to deliberately take it over.

    Returns:
        The claimed issue, or an error message.
    """
    try:
        return await claim_issue(
            issue_id=issue_id,
            actor=actor,
            assignee=assignee,
            fail_if_claimed=fail_if_claimed,
        )
    except Exception as exc:
        return failure(f"claiming issue {issue_id} for {assignee!r}", exc)


@mcp.tool()
async def con_mcp_unassign_issue(issue_id: int, actor: str = ""):
    """Release an issue back to the unassigned pool.

    Args:
        issue_id: Issue to release (REQUIRED).
        actor: Who is releasing it.

    Returns:
        The updated issue, or an error message.
    """
    try:
        return await unassign_issue(issue_id, actor=actor)
    except Exception as exc:
        return failure(f"unassigning issue {issue_id}", exc)


@mcp.tool()
async def con_mcp_close_issue(
    issue_id: int,
    actor: str,
    reason: str = "Closed",
    force: bool = False,
):
    """Close an issue, recording why.

    Closing is what unblocks anything waiting on this issue, so do it as soon
    as the work is genuinely done. Calling it on an already-closed issue is
    harmless.

    Args:
        issue_id: Issue to close (REQUIRED).
        actor: Who is closing it (REQUIRED).
        reason: Why, e.g. "Completed", "Won't fix", "Duplicate".
        force: Required to close a pinned issue.

    Returns:
        The closed issue, or an error message.
    """
    try:
        return await close_issue(
            issue_id=issue_id, actor=actor, reason=reason, force=force
        )
    except Exception as exc:
        return failure(f"closing issue {issue_id}", exc)


@mcp.tool()
async def con_mcp_reopen_issue(issue_id: int, actor: str = "", status: str = "open"):
    """Reopen a closed issue.

    Args:
        issue_id: Issue to reopen (REQUIRED).
        actor: Who is reopening it.
        status: Status to return it to (default "open"). Cannot be "closed".

    Returns:
        The reopened issue. An issue that was not closed is returned unchanged.
    """
    try:
        return await reopen_issue(issue_id, actor=actor, status=status)
    except Exception as exc:
        return failure(f"reopening issue {issue_id}", exc)
