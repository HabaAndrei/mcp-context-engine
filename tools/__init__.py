"""MCP tool registration.

Importing this package executes each module, and the `@mcp.tool()` decorators
register the tools on the shared server instance. `main.py` imports it purely
for that side effect, so a new tool module only needs an import line here.
"""

from .comment import con_mcp_add_comment
from .dependency import con_mcp_add_dependency, con_mcp_remove_dependency
from .event import con_mcp_add_event
from .issue import (
    con_mcp_claim_issue,
    con_mcp_close_issue,
    con_mcp_create_child_issue,
    con_mcp_create_epic_with_children,
    con_mcp_create_issue,
    con_mcp_reopen_issue,
    con_mcp_unassign_issue,
    con_mcp_update_issue_fields,
)
from .label import con_mcp_add_labels, con_mcp_remove_labels, con_mcp_set_labels
from .query_tools import (
    con_mcp_find_dependency_cycles,
    con_mcp_get_blocked_issues,
    con_mcp_get_issue_details,
    con_mcp_get_issue_stats,
    con_mcp_get_issue_tree,
    con_mcp_get_ready_work,
    con_mcp_list_issues,
)

__all__ = [
    # Lifecycle
    "con_mcp_create_issue",
    "con_mcp_create_child_issue",
    "con_mcp_create_epic_with_children",
    "con_mcp_update_issue_fields",
    "con_mcp_claim_issue",
    "con_mcp_unassign_issue",
    "con_mcp_close_issue",
    "con_mcp_reopen_issue",
    # Labels
    "con_mcp_add_labels",
    "con_mcp_remove_labels",
    "con_mcp_set_labels",
    # Dependencies
    "con_mcp_add_dependency",
    "con_mcp_remove_dependency",
    # Discussion and audit
    "con_mcp_add_comment",
    "con_mcp_add_event",
    # Queries
    "con_mcp_get_issue_details",
    "con_mcp_get_ready_work",
    "con_mcp_get_blocked_issues",
    "con_mcp_list_issues",
    "con_mcp_get_issue_tree",
    "con_mcp_get_issue_stats",
    "con_mcp_find_dependency_cycles",
]
