"""The MCP tool surface.

Tools are invoked by a language model, so the contract differs from the service
layer's: a tool must never raise. A raised exception ends the model's turn with
nothing it can act on, whereas a returned sentence lets it correct itself and
try again.

Each tool is exercised through `.fn`, the plain function FastMCP wraps, so
these tests cover the tool's own logic without standing up a server.
"""

from __future__ import annotations

import json

from tools import (
    con_mcp_add_comment,
    con_mcp_add_dependency,
    con_mcp_add_labels,
    con_mcp_claim_issue,
    con_mcp_close_issue,
    con_mcp_create_epic_with_children,
    con_mcp_create_issue,
    con_mcp_get_issue_details,
    con_mcp_get_issue_stats,
    con_mcp_get_ready_work,
    con_mcp_list_issues,
    con_mcp_remove_dependency,
)


class TestHappyPath:
    async def test_create_returns_structured_data(self, db):
        """Tools return dicts, not str(dict).

        The previous implementation returned Python repr, which a client
        cannot parse back into structured content.
        """
        result = await con_mcp_create_issue.fn(title="Structured")

        assert isinstance(result, dict)
        assert result["title"] == "Structured"
        json.dumps(result)

    async def test_ready_work_reflects_dependencies(self, db):
        first = await con_mcp_create_issue.fn(title="First")
        second = await con_mcp_create_issue.fn(title="Second")
        await con_mcp_add_dependency.fn(
            issue_id=second["id"], depends_on_id=first["id"], dep_type="blocks"
        )

        ready = await con_mcp_get_ready_work.fn()
        assert [i["title"] for i in ready["issues"]] == ["First"]

        await con_mcp_close_issue.fn(issue_id=first["id"], actor="ana")

        ready = await con_mcp_get_ready_work.fn()
        assert [i["title"] for i in ready["issues"]] == ["Second"]

    async def test_epic_tool_returns_epic_and_children(self, db):
        result = await con_mcp_create_epic_with_children.fn(
            epic_kwargs={"title": "Auth"},
            children_kwargs=[{"title": "Login"}, {"title": "Tokens"}],
        )

        assert result["epic"]["issue_type"] == "epic"
        assert len(result["children"]) == 2
        json.dumps(result)

    async def test_details_include_related_data(self, db):
        issue = await con_mcp_create_issue.fn(title="Rich", labels=["api"])
        await con_mcp_add_comment.fn(issue_id=issue["id"], author="ana", text="a note")

        details = await con_mcp_get_issue_details.fn(issue_id=issue["id"])

        assert details["labels"] == ["api"]
        assert len(details["comments"]) == 1
        json.dumps(details)

    async def test_stats_tool_reports_the_board(self, db):
        await con_mcp_create_issue.fn(title="One")
        stats = await con_mcp_get_issue_stats.fn()

        assert stats["total"] == 1
        assert stats["ready"] == 1

    async def test_remove_dependency_reports_outcome(self, db):
        a = await con_mcp_create_issue.fn(title="A")
        b = await con_mcp_create_issue.fn(title="B")
        await con_mcp_add_dependency.fn(issue_id=a["id"], depends_on_id=b["id"])

        assert await con_mcp_remove_dependency.fn(
            issue_id=a["id"], depends_on_id=b["id"]
        ) == {"removed": True}


class TestErrorsBecomeMessages:
    async def test_missing_issue_returns_a_message(self, db):
        result = await con_mcp_get_issue_details.fn(issue_id=4242)

        assert isinstance(result, str)
        assert "4242" in result

    async def test_blank_title_returns_a_message(self, db):
        result = await con_mcp_create_issue.fn(title="")

        assert isinstance(result, str)
        assert "title" in result.lower()

    async def test_invalid_priority_returns_a_message(self, db):
        result = await con_mcp_create_issue.fn(title="Bad", priority=9)

        assert isinstance(result, str)
        assert "priority" in result.lower()

    async def test_cycle_returns_a_message_naming_the_problem(self, db):
        a = await con_mcp_create_issue.fn(title="A")
        b = await con_mcp_create_issue.fn(title="B")
        await con_mcp_add_dependency.fn(
            issue_id=a["id"], depends_on_id=b["id"], dep_type="blocks"
        )

        result = await con_mcp_add_dependency.fn(
            issue_id=b["id"], depends_on_id=a["id"], dep_type="blocks"
        )

        assert isinstance(result, str)
        assert "cycle" in result.lower()

    async def test_claiming_taken_work_returns_a_message(self, db):
        issue = await con_mcp_create_issue.fn(title="Contested")
        await con_mcp_claim_issue.fn(issue_id=issue["id"], actor="ana", assignee="ana")

        result = await con_mcp_claim_issue.fn(
            issue_id=issue["id"], actor="bo", assignee="bo"
        )

        assert isinstance(result, str)
        assert "already claimed" in result

    async def test_bare_string_label_returns_a_message(self, db):
        issue = await con_mcp_create_issue.fn(title="Careful")

        result = await con_mcp_add_labels.fn(issue_id=issue["id"], labels="backend")

        assert isinstance(result, str)
        assert "list of strings" in result

    async def test_bad_status_filter_returns_a_message(self, db):
        result = await con_mcp_list_issues.fn(status="almost-done")

        assert isinstance(result, str)
        assert "status" in result.lower()


class TestRegistration:
    async def test_every_tool_is_registered_with_the_server(self, db):
        from mcp_engine import mcp
        import tools

        registered = set(await mcp.get_tools())

        assert set(tools.__all__) == registered
