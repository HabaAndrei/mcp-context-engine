"""Event MCP tools."""

from mcp_engine import mcp

from database.services import add_event

from ._common import failure


@mcp.tool()
async def con_mcp_add_event(
    issue_id: int,
    event_type: str,
    actor: str,
    old_value: str | None = None,
    new_value: str | None = None,
    comment: str | None = None,
):
    """Record a custom entry in an issue's audit trail.

    Creates, updates, closures and dependency changes are logged automatically.
    Use this for things the tracker has no opinion about - "deployed",
    "reviewed", "escalated".

    Args:
        issue_id: Issue the event belongs to (REQUIRED).
        event_type: A short dotted label, e.g. "review.approved" (REQUIRED).
        actor: Who performed the action (REQUIRED).
        old_value: Prior value, if the event describes a change.
        new_value: New value, if the event describes a change.
        comment: Free-text context.

    Returns:
        The created event with its id and timestamp, or an error message.
    """
    try:
        return await add_event(
            issue_id=issue_id,
            event_type=event_type,
            actor=actor,
            old_value=old_value,
            new_value=new_value,
            comment=comment,
        )
    except Exception as exc:
        return failure(f"adding event {event_type!r} to issue {issue_id}", exc)
