from mcp_engine import mcp
from logger import log_error
from database.services import add_comment


@mcp.tool()
async def con_mcp_add_comment(issue_id: int, author: str, text: str):
    """Add a comment to an existing issue.

    Comments are used for discussions, updates, and notes on issues. Creates an
    event log entry when added.

    Args:
        issue_id: ID of the issue to comment on (REQUIRED)
        author: Username or identifier of the comment author (REQUIRED, defaults
            to "unknown" if empty)
        text: Comment text content (REQUIRED, cannot be empty)

    Returns:
        String representation of created comment with ID and timestamp, or error
        if issue doesn't exist.
    """
    try:
        return str(await add_comment(issue_id=issue_id, author=author, text=text))
    except Exception as e:
        log_error(f" adding comment to issue {issue_id}: {type(e).__name__}: {e}")
        return f"Error adding comment to issue {issue_id}: {type(e).__name__}: {e}"
