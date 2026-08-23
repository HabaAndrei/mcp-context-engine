"""Label MCP tools."""

from mcp_engine import mcp

from database.services import add_labels, remove_labels, set_labels

from ._common import failure


@mcp.tool()
async def con_mcp_add_labels(issue_id: int, labels: list[str]):
    """Add labels to an issue, keeping any it already has.

    Args:
        issue_id: Issue to label (REQUIRED).
        labels: Label strings, e.g. ["bug", "urgent"]. Blanks and duplicates
            are dropped; re-adding an existing label is harmless.

    Returns:
        {"issue_id": int, "labels_added": [...]} or an error message.
    """
    try:
        applied = await add_labels(issue_id=issue_id, labels=labels)
        return {"issue_id": issue_id, "labels_added": applied}
    except Exception as exc:
        return failure(f"adding labels to issue {issue_id}", exc)


@mcp.tool()
async def con_mcp_remove_labels(issue_id: int, labels: list[str]):
    """Remove specific labels from an issue.

    Args:
        issue_id: Issue to update (REQUIRED).
        labels: Label strings to remove. Labels not present are ignored.

    Returns:
        {"issue_id": int, "removed": int} or an error message.
    """
    try:
        removed = await remove_labels(issue_id=issue_id, labels=labels)
        return {"issue_id": issue_id, "removed": removed}
    except Exception as exc:
        return failure(f"removing labels from issue {issue_id}", exc)


@mcp.tool()
async def con_mcp_set_labels(issue_id: int, labels: list[str]):
    """Replace an issue's labels with exactly this set.

    Args:
        issue_id: Issue to update (REQUIRED).
        labels: The complete new set. Pass [] to clear all labels.

    Returns:
        {"issue_id": int, "labels": [...]} or an error message.
    """
    try:
        applied = await set_labels(issue_id=issue_id, labels=labels)
        return {"issue_id": issue_id, "labels": applied}
    except Exception as exc:
        return failure(f"setting labels on issue {issue_id}", exc)
