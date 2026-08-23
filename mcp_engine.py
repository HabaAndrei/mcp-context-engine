"""The shared FastMCP server instance.

Kept in its own module so `tools/*` can import `mcp` to register handlers
without importing `main`, which would be circular.

The `instructions` text is the model's first and often only description of what
this server is for. It is written to steer behaviour - lead with ready work,
close things promptly - rather than to restate the tool list, which the client
already receives in full.
"""

from fastmcp import FastMCP

mcp = FastMCP(
    name="ContextEngine",
    instructions="""
Persistent issue tracker and context engine for coding agents.

Use it as working memory that outlives the conversation. Anything recorded here
is still available in a later session, after a context reset, and to any other
agent on the same database.

Suggested loop:

1. Starting or resuming: call con_mcp_get_issue_stats for the shape of the
   board, then con_mcp_get_ready_work to see what can be started right now.
2. Planning something large: con_mcp_create_epic_with_children records the
   whole breakdown in one atomic call.
3. Before working: con_mcp_claim_issue, so no other agent takes the same task.
4. While working: con_mcp_add_comment for decisions and their reasons. That
   reasoning is what you will most want, and least have, when you return.
5. When genuinely done: con_mcp_close_issue. Closing is what unblocks whatever
   was waiting.
6. When something cannot proceed: con_mcp_add_dependency with dep_type
   "blocks", so the obstacle is recorded rather than remembered.

Worth knowing:

- Ready work means open with every "blocks" dependency closed. Only "blocks"
  gates execution; "parent-child" groups issues without ordering them, so a
  task in an unfinished epic is still startable.
- Priorities run 0 (most urgent) to 4 (least).
- If con_mcp_get_ready_work comes back empty, call con_mcp_get_blocked_issues
  to find out what is holding things up.
""",
)
