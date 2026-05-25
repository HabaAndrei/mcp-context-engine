from mcp_engine import mcp
from logger import log_error
from database.services import (
    add_dependency,
    remove_dependency,
    DEP_BLOCKS
)


@mcp.tool()
async def con_mcp_add_dependency(
    issue_id: int,
    depends_on_id: int,
    *,
    dep_type: str = DEP_BLOCKS,
    created_by: str = "",
    metadata: dict | None = None,
    thread_id: str = "",
):
    """Add a dependency relationship between two issues.

    Creates a directed edge from issue_id to depends_on_id. Different dependency
    types represent different relationships (blocks, related, parent-child, etc.).

    Args:
        issue_id: Source issue ID (REQUIRED)
        depends_on_id: Target issue ID that this issue depends on (REQUIRED)
        dep_type: Type of dependency relationship, one of:
            - "blocks" (default): This issue blocks the target issue
            - "parent-child": Hierarchical relationship (child -> parent)
            - "related": General relationship between issues
            - "duplicates": This issue duplicates the target
            - "supersedes": This issue supersedes/replaces the target
        created_by: Username of person creating the dependency (optional)
        metadata: Additional JSON metadata about the dependency (optional)
        thread_id: Thread/conversation ID for tracking context (optional)

    Returns:
        String representation of created dependency, or error if issues don't exist.
    """
    try:
        return str(await add_dependency(
            issue_id=issue_id,
            depends_on_id=depends_on_id,
            dep_type=dep_type,
            created_by=created_by,
            metadata=metadata,
            thread_id=thread_id
        ))
    except Exception as e:
        log_error(f" adding dependency {issue_id} -> {depends_on_id} ({dep_type}): {type(e).__name__}: {e}")
        return f"Error adding dependency: {type(e).__name__}: {e}"


@mcp.tool()
async def con_mcp_remove_dependency(
    issue_id: int,
    depends_on_id: int
):
    """Remove a dependency relationship between two issues.

    Removes the dependency edge from issue_id to depends_on_id regardless of type.

    Args:
        issue_id: Source issue ID (REQUIRED)
        depends_on_id: Target issue ID (REQUIRED)

    Returns:
        True if dependency was removed, False if it didn't exist.
    """
    try:
        return str(await remove_dependency(
            issue_id=issue_id,
            depends_on_id=depends_on_id
        ))
    except Exception as e:
        log_error(f" removing dependency {issue_id} -> {depends_on_id}: {type(e).__name__}: {e}")
        return f"Error removing dependency: {type(e).__name__}: {e}"