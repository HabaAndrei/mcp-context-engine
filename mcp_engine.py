from fastmcp import FastMCP


mcp = FastMCP(
    name="MyTasksEngine",
    instructions="""
    Project management and issue tracking MCP server.

    Tools:
    - con_mcp_create_issue: Create tasks/subtasks/epics with priorities (P0-P4),
    status tracking, labels, dependencies, time estimates, and assignees.
    - con_mcp_create_child_issue: Create a child issue under a parent for
      hierarchical task organization (auto-creates parent-child dependency).
    - con_mcp_create_epic_with_children: Create an epic with multiple child tasks
        in one operation, automatically establishing parent-child relationships.
    - con_mcp_update_issue_fields: Update one or more fields of an existing issue
        (status, priority, title, assignee, description, notes, etc.).
    - con_mcp_claim_issue: Claim an issue (assign and set to in_progress).
    - con_mcp_close_issue: Close an issue with a reason.
    - con_mcp_add_labels: Add labels/tags to an existing issue.
    - con_mcp_remove_labels: Remove specific labels from an issue.
    - con_mcp_set_labels: Replace all labels on an issue with a new set.
    - con_mcp_add_dependency: Add dependency relationships between issues
        (blocks, parent-child, related, duplicates, supersedes).
    - con_mcp_remove_dependency: Remove a dependency relationship between issues.
    - con_mcp_add_comment: Add a comment/note to an issue for discussions and updates.
    - con_mcp_add_event: Add a custom event log entry to track actions and changes.
    - con_mcp_get_issue_details: Get comprehensive details about an issue including
        all fields, labels, comments, dependencies, dependents, and parent.
    """,
)