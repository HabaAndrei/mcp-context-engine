"""Comment MCP tools."""

from mcp_engine import mcp

from database.services import add_comment

from ._common import failure


@mcp.tool()
async def con_mcp_add_comment(issue_id: int, author: str, text: str):
    """Add a comment to an issue.

    Comments are the place to record why something was decided. That reasoning
    is what an agent most often needs, and least often still has, when it picks
    the issue up in a later session.

    Args:
        issue_id: Issue to comment on (REQUIRED).
        author: Who is commenting. Recorded as "unknown" if blank.
        text: The comment body (REQUIRED, cannot be blank).

    Returns:
        The created comment with its id and timestamp, or an error message.
    """
    try:
        return await add_comment(issue_id=issue_id, author=author, text=text)
    except Exception as exc:
        return failure(f"adding comment to issue {issue_id}", exc)
