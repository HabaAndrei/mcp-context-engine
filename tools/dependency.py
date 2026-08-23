"""Dependency MCP tools."""

from mcp_engine import mcp

from database.services import DEP_BLOCKS, add_dependency, remove_dependency

from ._common import failure


@mcp.tool()
async def con_mcp_add_dependency(
    issue_id: int,
    depends_on_id: int,
    dep_type: str = DEP_BLOCKS,
    created_by: str = "",
    metadata: dict | None = None,
    thread_id: str = "",
):
    """Relate one issue to another.

    Creates the edge issue_id -> depends_on_id. The pair is unique, so calling
    this again for the same two issues updates the existing edge rather than
    adding a second one.

    Args:
        issue_id: The dependent issue (REQUIRED).
        depends_on_id: The issue it points at (REQUIRED).
        dep_type: One of:
            - "blocks" (default): issue_id cannot start until depends_on_id
              closes. This is the only type that affects ready work.
            - "parent-child": issue_id is a child of depends_on_id.
            - "related", "duplicates", "supersedes": annotations only.
        created_by: Who added the edge (optional).
        metadata: Arbitrary JSON stored with the edge (optional).
        thread_id: Conversation identifier for provenance (optional).

    Returns:
        The created edge, or an error message. Rejected if either issue is
        missing, if an issue points at itself, or if a "blocks" or
        "parent-child" edge would create a cycle.
    """
    try:
        return await add_dependency(
            issue_id=issue_id,
            depends_on_id=depends_on_id,
            dep_type=dep_type,
            created_by=created_by,
            metadata=metadata,
            thread_id=thread_id,
        )
    except Exception as exc:
        return failure(
            f"adding {dep_type} dependency {issue_id} -> {depends_on_id}", exc
        )


@mcp.tool()
async def con_mcp_remove_dependency(issue_id: int, depends_on_id: int):
    """Remove the edge between two issues, whatever its type.

    Args:
        issue_id: The dependent issue (REQUIRED).
        depends_on_id: The issue it points at (REQUIRED).

    Returns:
        {"removed": bool} - False when there was no such edge.
    """
    try:
        removed = await remove_dependency(
            issue_id=issue_id, depends_on_id=depends_on_id
        )
        return {"removed": removed}
    except Exception as exc:
        return failure(f"removing dependency {issue_id} -> {depends_on_id}", exc)
