from mcp_engine import mcp
from logger import log_error
from database.services import (
    add_event
)


@mcp.tool()
async def con_mcp_add_event(
    issue_id: int,
    *,
    event_type: str,
    actor: str,
    old_value: str | None = None,
    new_value: str | None = None,
    comment: str | None = None,
):
    """Add a custom event log entry to an issue.

    Events track the history of changes and actions on issues. Most tools automatically
    create events, but this allows adding custom event entries for special cases.

    Args:
        issue_id: ID of the issue to add event to (REQUIRED)
        event_type: Type of event, e.g. "update.status", "comment.add", "create", "close",
            or custom types like "approval", "review", etc. (REQUIRED)
        actor: Username performing the action (REQUIRED)
        old_value: Previous value before the change (optional)
        new_value: New value after the change (optional)
        comment: Additional context or description of the event (optional)

    Returns:
        String representation of created event with ID and timestamp, or error if
        issue doesn't exist.
    """
    try:
        return str(await add_event(
            issue_id=issue_id,
            event_type=event_type,
            actor=actor,
            old_value=old_value,
            new_value=new_value,
            comment=comment,
        ))
    except Exception as e:
        log_error(f" adding event '{event_type}' to issue {issue_id}: {type(e).__name__}: {e}")
        return f"Error adding event to issue {issue_id}: {type(e).__name__}: {e}"
