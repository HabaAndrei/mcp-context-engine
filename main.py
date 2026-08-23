"""Entry point for the Context MCP server.

Reads the transport from CON_MCP_TRANSPORT ("stdio" by default, or "http") and
starts the server. Importing `tools` is what registers the tool handlers; it
looks unused, hence the noqa.

The database engine is built lazily on the first tool call, so an unreachable
database surfaces as a tool error rather than preventing startup and leaving
the client with no server at all.
"""

from config_env import env_vars
from mcp_engine import mcp

import tools  # noqa: F401  - imported for its @mcp.tool() registration side effects


def run() -> None:
    """Start the MCP server on the configured transport."""
    mcp.run(transport=env_vars.get("CON_MCP_TRANSPORT", "stdio"))


if __name__ == "__main__":
    run()
