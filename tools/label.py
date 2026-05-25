from mcp_engine import mcp
from logger import log_error
from database.services import (
    add_labels,
    remove_labels,
    set_labels
)
from typing import Iterable


@mcp.tool()
async def con_mcp_add_labels(issue_id: int, labels: Iterable[str]):
    """Add labels/tags to an existing issue.

    Args:
        issue_id: ID of the issue to add labels to (REQUIRED)
        labels: List of label strings to add, e.g. ["bug", "urgent", "backend"]
            Empty labels are skipped. Duplicate labels are handled automatically.

    Returns:
        Success message or error if issue doesn't exist.
    """
    try:
        return str(await add_labels(issue_id=issue_id, labels=labels))
    except Exception as e:
        log_error(f" adding labels to issue {issue_id}: {type(e).__name__}: {e}")
        return f"Error adding labels to issue {issue_id}: {type(e).__name__}: {e}"


@mcp.tool()
async def con_mcp_remove_labels(issue_id: int, labels: Iterable[str]):
    """Remove labels/tags from an existing issue.

    Args:
        issue_id: ID of the issue to remove labels from (REQUIRED)
        labels: List of label strings to remove, e.g. ["bug", "urgent"]
            Only existing labels will be removed. Non-existent labels are ignored.

    Returns:
        Number of labels removed, or error if issue doesn't exist.
    """
    try:
        return str(await remove_labels(issue_id=issue_id, labels=labels))
    except Exception as e:
        log_error(f" removing labels from issue {issue_id}: {type(e).__name__}: {e}")
        return f"Error removing labels from issue {issue_id}: {type(e).__name__}: {e}"


@mcp.tool()
async def con_mcp_set_labels(issue_id: int, labels: Iterable[str]):
    """Replace all labels on an issue with a new set.

    Removes all existing labels and sets the provided ones. Useful for completely
    redefining an issue's labels.

    Args:
        issue_id: ID of the issue to update labels for (REQUIRED)
        labels: List of label strings to set, e.g. ["frontend", "high-priority"]
            All existing labels are removed first, then these are added.
            Pass empty list [] to remove all labels.

    Returns:
        Success message or error if issue doesn't exist.
    """
    try:
        return str(await set_labels(issue_id=issue_id, labels=labels))
    except Exception as e:
        log_error(f" setting labels on issue {issue_id}: {type(e).__name__}: {e}")
        return f"Error setting labels on issue {issue_id}: {type(e).__name__}: {e}"