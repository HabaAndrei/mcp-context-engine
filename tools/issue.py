from mcp_engine import mcp
from logger import log_error
from database.services import (
    create_issue,
    STATUS_OPEN,
    create_child_issue,
    create_epic_with_children,
    update_issue_fields,
    claim_issue,
    close_issue,
    IssueKwargs,
)
from typing import Literal


@mcp.tool()
async def con_mcp_create_issue(
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
):
    """Create a new issue/task in the project management system.

    Args:
        title: Issue title/summary (REQUIRED, max 500 chars)
        description: Detailed description (optional)
        acceptance_criteria: Conditions for completion (optional)
        notes: Additional notes (optional)
        status: One of: "open" (default), "in_progress", "blocked", "deferred", "closed"
        priority: 0-4 where 0=highest, 4=lowest (default: 2)
        issue_type: "task" (default), "subtask", or "epic"
        assignee: Username of assigned person (optional)
        estimated_minutes: Time estimate in minutes (optional)
        created_by: Username of creator (optional)
        pinned: Pin to top of lists (default: False)
        labels: List of tags, e.g. ["backend", "bug"] (optional)
        dependencies: List of [issue_id, type] pairs where type is one of:
            "blocks", "parent-child", "related", "duplicates", "supersedes"
            Example: [[123, "blocks"], [45, "parent-child"]]
            Note: Use nested lists instead of tuples for JSON compatibility.

    Returns:
        String representation of created issue with ID and timestamps, or error message.
    """

    try:
        return str(
            await create_issue(
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
        )
    except Exception as e:
        log_error(f" creating issue '{title}': {type(e).__name__}: {e}")
        return f"Error creating issue: {type(e).__name__}: {e}"


@mcp.tool()
async def con_mcp_create_child_issue(
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
):
    """Create a child issue under a parent issue (for hierarchical task organization).

    Args:
        parent_id: ID of the parent issue (REQUIRED)
        title: Issue title/summary (REQUIRED, max 500 chars)
        description: Detailed description (optional)
        acceptance_criteria: Conditions for completion (optional)
        notes: Additional notes (optional)
        status: One of: "open" (default), "in_progress", "blocked", "deferred", "closed"
        priority: 0-4 where 0=highest, 4=lowest (default: 2)
        issue_type: "task" (default), "subtask", or "epic"
        assignee: Username of assigned person (optional)
        estimated_minutes: Time estimate in minutes (optional)
        created_by: Username of creator (optional)
        pinned: Pin to top of lists (default: False)
        labels: List of tags, e.g. ["backend", "bug"] (optional)

    Returns:
        String representation of created child issue with auto-created parent-child
        dependency, or error message if parent doesn't exist.
    """
    try:
        return str(
            await create_child_issue(
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
        )
    except Exception as e:
        log_error(
            f" creating child issue '{title}' under parent {parent_id}: {type(e).__name__}: {e}"
        )
        return f"Error creating child issue: {type(e).__name__}: {e}"


@mcp.tool()
async def con_mcp_create_epic_with_children(
    epic_kwargs: IssueKwargs,
    children_kwargs: list[IssueKwargs],
    *,
    epic_labels: list[str] | None = None,
    child_labels: list[str] | None = None,
):
    """Create an epic with multiple child tasks in one operation.

    Convenience tool for creating a large feature (epic) with its child tasks together.
    Automatically creates parent-child dependencies from each child to the epic.

    Args:
        epic_kwargs: Dictionary with epic issue fields. Available fields:
            - title: Epic title (REQUIRED)
            - description, acceptance_criteria, notes: Text fields
            - status: "open", "in_progress", "blocked", "deferred", "closed"
            - priority: 0-4 (default: 2)
            - assignee: Username
            - estimated_minutes: Time estimate
            - created_by: Creator username
            - pinned: Boolean
            Note: issue_type is auto-set to "epic"

        children_kwargs: List of dictionaries, each with child issue fields (same
            fields as epic_kwargs). Example: [{"title": "Task 1"}, {"title": "Task 2"}]

        epic_labels: Labels to apply to the epic (optional)
        child_labels: Labels to apply to ALL children (optional)

    Returns:
        String representation of tuple (epic_issue, [child_issues]), or error message.

    Example:
        con_mcp_create_epic_with_children(
            epic_kwargs={"title": "Build Auth System", "priority": 1},
            children_kwargs=[
                {"title": "Login Page", "description": "Create login UI"},
                {"title": "JWT Tokens", "description": "Implement tokens"}
            ],
            epic_labels=["backend"],
            child_labels=["auth"]
        )
    """
    try:
        return str(
            await create_epic_with_children(
                epic_kwargs=epic_kwargs,
                children_kwargs=children_kwargs,
                epic_labels=epic_labels,
                child_labels=child_labels,
            )
        )
    except Exception as e:
        log_error(f" creating epic with children: {type(e).__name__}: {e}")
        return f"Error creating epic with children: {type(e).__name__}: {e}"


@mcp.tool()
async def con_mcp_update_issue_fields(
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
):
    """Update one or more fields of an existing issue.

    Only provide fields you want to update. Unchanged fields can be omitted.
    Creates event log entries for each changed field.

    Args:
        issue_id: ID of the issue to update (REQUIRED)
        actor: Username performing the update (optional)
        status: New status: "open", "in_progress", "blocked", "deferred", "closed"
        priority: New priority 0-4 where 0=highest
        title: New title (max 500 chars)
        assignee: New assignee username
        description: New description text
        acceptance_criteria: New acceptance criteria
        notes: New notes
        estimated_minutes: New time estimate in minutes

    Returns:
        String representation of updated issue, or error if issue doesn't exist.
    """
    try:
        return str(
            await update_issue_fields(
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
        )
    except Exception as e:
        log_error(f" updating issue {issue_id}: {type(e).__name__}: {e}")
        return f"Error updating issue {issue_id}: {type(e).__name__}: {e}"


@mcp.tool()
async def con_mcp_claim_issue(
    issue_id: int,
    *,
    actor: str,
    assignee: str,
    fail_if_claimed: bool = True,
):
    """Claim an issue for work (assign to someone and set status to in_progress).

    Convenience tool that assigns an issue and marks it as in_progress in one operation.

    Args:
        issue_id: ID of the issue to claim (REQUIRED)
        actor: Username performing the claim action (REQUIRED)
        assignee: Username to assign the issue to (REQUIRED)
        fail_if_claimed: If True (default), raise error if issue is already assigned
            to a different person. If False, reassign regardless.

    Returns:
        String representation of claimed issue, or error if already claimed (when
        fail_if_claimed=True) or issue doesn't exist.
    """
    try:
        return str(
            await claim_issue(
                issue_id=issue_id,
                actor=actor,
                assignee=assignee,
                fail_if_claimed=fail_if_claimed,
            )
        )
    except Exception as e:
        log_error(f" claiming issue {issue_id} for {assignee}: {type(e).__name__}: {e}")
        return f"Error claiming issue {issue_id}: {type(e).__name__}: {e}"


@mcp.tool()
async def con_mcp_close_issue(
    issue_id: int,
    *,
    actor: str,
    reason: str = "Closed",
    force: bool = False,
):
    """Close an issue with a reason.

    Sets issue status to closed and creates an event log entry with the reason.

    Args:
        issue_id: ID of the issue to close (REQUIRED)
        actor: Username performing the close action (REQUIRED)
        reason: Reason for closing, e.g. "Completed", "Won't fix", "Duplicate" (default: "Closed")
        force: If True, allows closing pinned issues. If False (default), pinned
            issues cannot be closed.

    Returns:
        String representation of closed issue, or error if issue doesn't exist or
        is pinned (when force=False).
    """
    try:
        return str(
            await close_issue(
                issue_id=issue_id,
                actor=actor,
                reason=reason,
                force=force,
            )
        )
    except Exception as e:
        log_error(f" closing issue {issue_id}: {type(e).__name__}: {e}")
        return f"Error closing issue {issue_id}: {type(e).__name__}: {e}"
