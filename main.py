from config_env import env_vars

from mcp_engine import mcp
import tools  # noqa   =>   Import registers all tools via @mcp.tool() decorators



mcp.run(transport=env_vars.get("CON_MCP_TRANSPORT", "stdio"))