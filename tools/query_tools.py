from database.services import get_issue_details
from mcp_engine import mcp
from logger import log_error


@mcp.tool()
async def con_mcp_get_issue_details(issue_id: int, include_nested_deps: bool = True):
    """Get comprehensive details about an issue.

    Returns complete information about an issue including all fields, labels, comments,
    dependencies, dependents, and parent relationship. This is the primary query tool
    for retrieving full issue information.

    Args:
        issue_id: ID of the issue to retrieve (REQUIRED)
        include_nested_deps: If True (default), includes dependency and dependent info
            for each related issue. If False, only includes direct relationships.

    Returns:
        Dictionary containing:
        - All issue fields (id, title, description, status, priority, etc.)
        - labels: List of label strings
        - comments: List of comment objects with id, author, text, created_at
        - dependencies: List of issues this issue depends on, with dependency_type
        - dependents: List of issues that depend on this issue, with dependency_type
        - parent: Parent issue ID (if this is a child issue), or None
        - If include_nested_deps=True: Each dependency/dependent includes its own
          dependencies and dependents lists

        Returns error message if issue doesn't exist.
    """
    try:
        return str(
            await get_issue_details(
                issue_id=issue_id, include_nested_deps=include_nested_deps
            )
        )
    except Exception as e:
        log_error(f" getting issue details for {issue_id}: {type(e).__name__}: {e}")
        return f"Error getting issue details for {issue_id}: {type(e).__name__}: {e}"
