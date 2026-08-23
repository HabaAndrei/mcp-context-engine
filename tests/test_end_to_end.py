"""End-to-end checks against a real server over the MCP protocol.

The other test modules call service and tool functions directly, which leaves
one gap: whether an actual client can complete a session against an actual
server process. These tests launch `main.py` as a subprocess, speak MCP to it
over stdio, and drive the workflow an agent would really follow.

Slower than the rest of the suite because each case starts a process, so they
are marked `integration`. Deselect with `-m "not integration"`.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from sqlalchemy import create_engine

from database.models.__utils__ import Base

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parent.parent


def unwrap(result):
    """Extract the payload from a CallToolResult.

    Tools return dicts on success and a plain string on failure, so both shapes
    have to survive the trip back.
    """
    if getattr(result, "structured_content", None) is not None:
        content = result.structured_content
        # FastMCP wraps non-object return values under "result".
        return content.get("result", content) if isinstance(content, dict) else content
    if result.content and hasattr(result.content[0], "text"):
        try:
            return json.loads(result.content[0].text)
        except json.JSONDecodeError:
            return result.content[0].text
    return None


@pytest_asyncio.fixture
async def server(tmp_path):
    """Yield a connected client talking to a freshly-started server process."""
    db_path = tmp_path / "e2e.db"

    # Build the schema up front; the server does not migrate on startup.
    sync_engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()

    transport = StdioTransport(
        command=sys.executable,
        args=[str(REPO_ROOT / "main.py")],
        cwd=str(REPO_ROOT),
        env={
            **os.environ,
            "CON_MCP_DB_TYPE": "sqlite",
            "CON_MCP_SQLITE_PATH": str(db_path),
            "CON_MCP_TRANSPORT": "stdio",
            "PYTHONPATH": str(REPO_ROOT),
        },
    )

    async with Client(transport) as client:
        yield client


class TestProtocol:
    async def test_handshake_exposes_every_tool(self, server):
        import tools

        names = {tool.name for tool in await server.list_tools()}
        assert names == set(tools.__all__)

    async def test_tools_advertise_descriptions(self, server):
        """The docstrings are how the model decides which tool to call."""
        for tool in await server.list_tools():
            assert tool.description, f"{tool.name} has no description"


class TestAgentWorkflow:
    async def test_plan_execute_and_unblock(self, server):
        """The full loop: plan, discover, claim, close, re-discover."""
        created = unwrap(
            await server.call_tool(
                "con_mcp_create_epic_with_children",
                {
                    "epic_kwargs": {"title": "Authentication", "priority": 1},
                    "children_kwargs": [
                        {"title": "Login endpoint"},
                        {"title": "Auth tests"},
                    ],
                    "child_labels": ["auth"],
                },
            )
        )
        login, auth_tests = (child["id"] for child in created["children"])

        # Tests cannot start until the endpoint exists.
        await server.call_tool(
            "con_mcp_add_dependency",
            {"issue_id": auth_tests, "depends_on_id": login, "dep_type": "blocks"},
        )

        ready = unwrap(await server.call_tool("con_mcp_get_ready_work", {}))
        offered = {issue["title"] for issue in ready["issues"]}
        assert offered == {"Login endpoint"}, "only the unblocked task is startable"

        await server.call_tool(
            "con_mcp_claim_issue",
            {"issue_id": login, "actor": "ana", "assignee": "ana"},
        )
        await server.call_tool(
            "con_mcp_close_issue",
            {"issue_id": login, "actor": "ana", "reason": "Completed"},
        )

        ready = unwrap(await server.call_tool("con_mcp_get_ready_work", {}))
        assert {i["title"] for i in ready["issues"]} == {"Auth tests"}

    async def test_dependency_metadata_survives_the_round_trip(self, server):
        first = unwrap(await server.call_tool("con_mcp_create_issue", {"title": "A"}))
        second = unwrap(await server.call_tool("con_mcp_create_issue", {"title": "B"}))

        edge = unwrap(
            await server.call_tool(
                "con_mcp_add_dependency",
                {
                    "issue_id": first["id"],
                    "depends_on_id": second["id"],
                    "metadata": {"reason": "shares a schema"},
                },
            )
        )
        assert edge["metadata"] == {"reason": "shares a schema"}

    async def test_comments_and_labels_are_readable_back(self, server):
        issue = unwrap(
            await server.call_tool(
                "con_mcp_create_issue", {"title": "Documented", "labels": ["api"]}
            )
        )
        await server.call_tool(
            "con_mcp_add_comment",
            {"issue_id": issue["id"], "author": "ana", "text": "Chose JWT"},
        )

        details = unwrap(
            await server.call_tool(
                "con_mcp_get_issue_details", {"issue_id": issue["id"]}
            )
        )
        assert details["labels"] == ["api"]
        assert details["comments"][0]["text"] == "Chose JWT"


class TestFailuresReachTheClient:
    async def test_missing_issue_returns_a_message(self, server):
        result = unwrap(
            await server.call_tool("con_mcp_get_issue_details", {"issue_id": 99999})
        )
        assert isinstance(result, str)
        assert "99999" in result

    async def test_contested_claim_is_refused(self, server):
        issue = unwrap(
            await server.call_tool("con_mcp_create_issue", {"title": "Contested"})
        )
        await server.call_tool(
            "con_mcp_claim_issue",
            {"issue_id": issue["id"], "actor": "ana", "assignee": "ana"},
        )

        result = unwrap(
            await server.call_tool(
                "con_mcp_claim_issue",
                {"issue_id": issue["id"], "actor": "bo", "assignee": "bo"},
            )
        )
        assert isinstance(result, str)
        assert "already claimed" in result

    async def test_cycle_is_refused_with_an_explanation(self, server):
        first = unwrap(await server.call_tool("con_mcp_create_issue", {"title": "A"}))
        second = unwrap(await server.call_tool("con_mcp_create_issue", {"title": "B"}))
        await server.call_tool(
            "con_mcp_add_dependency",
            {
                "issue_id": first["id"],
                "depends_on_id": second["id"],
                "dep_type": "blocks",
            },
        )

        result = unwrap(
            await server.call_tool(
                "con_mcp_add_dependency",
                {
                    "issue_id": second["id"],
                    "depends_on_id": first["id"],
                    "dep_type": "blocks",
                },
            )
        )
        assert isinstance(result, str)
        assert "cycle" in result.lower()

    async def test_a_failed_call_does_not_kill_the_session(self, server):
        """A tool error must leave the connection usable."""
        await server.call_tool("con_mcp_get_issue_details", {"issue_id": 99999})

        stats = unwrap(await server.call_tool("con_mcp_get_issue_stats", {}))
        assert stats["total"] == 0


class TestPersistence:
    async def test_state_survives_a_server_restart(self, tmp_path):
        """The point of the whole project: memory outliving the process."""
        db_path = tmp_path / "restart.db"
        sync_engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(sync_engine)
        sync_engine.dispose()

        transport = StdioTransport(
            command=sys.executable,
            args=[str(REPO_ROOT / "main.py")],
            cwd=str(REPO_ROOT),
            env={
                **os.environ,
                "CON_MCP_DB_TYPE": "sqlite",
                "CON_MCP_SQLITE_PATH": str(db_path),
                "CON_MCP_TRANSPORT": "stdio",
                "PYTHONPATH": str(REPO_ROOT),
            },
        )

        async with Client(transport) as client:
            await client.call_tool(
                "con_mcp_create_issue",
                {"title": "Remember me", "priority": 0},
            )

        # New process, same database.
        async with Client(transport) as client:
            ready = unwrap(await client.call_tool("con_mcp_get_ready_work", {}))
            assert [i["title"] for i in ready["issues"]] == ["Remember me"]
