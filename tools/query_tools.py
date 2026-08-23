"""Read-only MCP tools.

`con_mcp_get_ready_work` is the one an agent should reach for most: it answers
"what should I do next?" in a single call, without the agent pulling the whole
board and working out the dependency order itself.

Every tool converts exceptions into a plain-language string. The MCP client is
a language model, so a readable message it can act on beats a stack trace that
ends the run.
"""

from database.services import (
    find_cycles,
    get_blocked_issues,
    get_issue_details,
    get_issue_stats,
    get_issue_tree,
    get_ready_work,
    list_issues,
)
from mcp_engine import mcp

from ._common import failure


@mcp.tool()
async def con_mcp_get_issue_details(issue_id: int, include_nested_deps: bool = True):
    """Get everything known about one issue.

    Args:
        issue_id: The issue to describe (REQUIRED).
        include_nested_deps: If True (default), each related issue also reports
            its own dependencies and dependents, giving one more hop of context
            without another call.

    Returns:
        All issue fields, plus:
        - labels: list of label strings
        - comments: list of {id, author, text, created_at}
        - dependencies: issues this one depends on, each with dependency_type
        - dependents: issues depending on this one, each with dependency_type
        - parent: parent issue id, or None
        - is_blocked: True if an unfinished issue blocks this one
    """
    try:
        return await get_issue_details(
            issue_id=issue_id, include_nested_deps=include_nested_deps
        )
    except Exception as exc:
        return failure(f"getting details for issue {issue_id}", exc)


@mcp.tool()
async def con_mcp_get_ready_work(
    assignee: str | None = None,
    limit: int = 20,
    include_epics: bool = False,
):
    """Get the issues that can be started right now, best first.

    An issue is ready when it is open and every issue it depends on through a
    "blocks" edge is closed. Belonging to an unfinished epic does not make a
    task unready, because parent-child expresses grouping rather than order.

    Use this at the start of a session, and after closing anything, to decide
    what to pick up next.

    Args:
        assignee: Restrict to this person's queue. Omit for the shared pool.
        limit: Maximum issues to return (default 20, capped at 500).
        include_epics: Include epics, which are normally excluded as containers
            with no directly actionable work.

    Returns:
        {"count": int, "issues": [{id, title, status, priority, issue_type,
        assignee, labels}]} ordered by pinned, then priority, then id - so the
        first entry is the best next task.
    """
    try:
        return await get_ready_work(
            assignee=assignee, limit=limit, include_epics=include_epics
        )
    except Exception as exc:
        return failure("getting ready work", exc)


@mcp.tool()
async def con_mcp_get_blocked_issues(limit: int = 20):
    """Get unfinished issues that are waiting on something, and what on.

    Use this when ready work is empty, to find out what is holding the board up.

    Args:
        limit: Maximum issues to return (default 20, capped at 500).

    Returns:
        {"count": int, "issues": [...]} where each issue carries a blocked_by
        list naming the unfinished issues blocking it.
    """
    try:
        return await get_blocked_issues(limit=limit)
    except Exception as exc:
        return failure("getting blocked issues", exc)


@mcp.tool()
async def con_mcp_list_issues(
    status: str | None = None,
    issue_type: str | None = None,
    assignee: str | None = None,
    priority_max: int | None = None,
    labels: list[str] | None = None,
    search: str | None = None,
    include_closed: bool = False,
    limit: int = 20,
    offset: int = 0,
):
    """Search and browse issues with filters.

    Args:
        status: Exact status: "open", "in_progress", "blocked", "deferred",
            "closed". Overrides include_closed.
        issue_type: "task", "subtask" or "epic".
        assignee: Exact assignee username.
        priority_max: Keep issues at least this urgent, e.g. 1 returns P0 and P1.
        labels: Keep only issues carrying ALL of these labels.
        search: Case-insensitive substring match on title and description.
        include_closed: Include closed issues (default False). Ignored when
            status is given.
        limit: Page size (default 20, capped at 500).
        offset: Rows to skip, for paging.

    Returns:
        {"total": int, "count": int, "limit": int, "offset": int,
        "issues": [...]} where total is the full match count before paging.
    """
    try:
        return await list_issues(
            status=status,
            issue_type=issue_type,
            assignee=assignee,
            priority_max=priority_max,
            labels=labels,
            search=search,
            include_closed=include_closed,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        return failure("listing issues", exc)


@mcp.tool()
async def con_mcp_get_issue_tree(root_id: int, max_depth: int = 5):
    """Get an issue together with its descendants.

    Walks parent-child edges downward. Use it to review an epic's breakdown in
    one call instead of fetching each child separately.

    Args:
        root_id: The issue at the top of the tree (REQUIRED).
        max_depth: Levels to walk below the root (default 5).

    Returns:
        The root summary with a nested children list, plus descendant_count.
    """
    try:
        return await get_issue_tree(root_id, max_depth=max_depth)
    except Exception as exc:
        return failure(f"building tree for issue {root_id}", exc)


@mcp.tool()
async def con_mcp_get_issue_stats():
    """Get a one-call overview of the whole board.

    Good for re-establishing context at the start of a session.

    Returns:
        {"total", "open", "closed", "ready", "blocked", "by_status", "by_type",
        "by_priority"} where ready and blocked are dependency-aware counts.
    """
    try:
        return await get_issue_stats()
    except Exception as exc:
        return failure("getting issue stats", exc)


@mcp.tool()
async def con_mcp_find_dependency_cycles(dep_type: str = "blocks"):
    """Find dependency cycles already stored in the database.

    New edges that would close a loop are refused, but data written by an older
    version or edited by hand can still contain one. A "blocks" cycle makes
    every issue in it permanently unready, which otherwise only shows up as
    work quietly missing from ready work.

    Args:
        dep_type: Edge type to inspect (default "blocks").

    Returns:
        {"dep_type": str, "count": int, "cycles": [[issue_id, ...], ...]}
    """
    try:
        return await find_cycles(dep_type=dep_type)
    except Exception as exc:
        return failure("finding dependency cycles", exc)
