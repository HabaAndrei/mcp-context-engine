"""Ready work, listing, labels and board statistics."""

from __future__ import annotations

import pytest

from database.domain import ValidationError
from database.services import (
    add_dependency,
    add_labels,
    claim_issue,
    close_issue,
    create_child_issue,
    create_issue,
    get_blocked_issues,
    get_issue_details,
    get_issue_stats,
    get_ready_work,
    list_issues,
    remove_labels,
    set_labels,
)


def titles(result) -> set[str]:
    return {issue["title"] for issue in result["issues"]}


class TestReadyWork:
    async def test_open_unblocked_issue_is_ready(self, db):
        await create_issue(title="Startable")
        assert titles(await get_ready_work()) == {"Startable"}

    async def test_blocked_issue_is_not_ready(self, db):
        task = await create_issue(title="Waiting")
        blocker = await create_issue(title="Blocker")
        await add_dependency(task["id"], blocker["id"], dep_type="blocks")

        assert "Waiting" not in titles(await get_ready_work())

    async def test_closing_the_blocker_releases_the_task(self, db):
        task = await create_issue(title="Waiting")
        blocker = await create_issue(title="Blocker")
        await add_dependency(task["id"], blocker["id"], dep_type="blocks")

        await close_issue(blocker["id"], actor="ana")

        assert "Waiting" in titles(await get_ready_work())

    async def test_all_blockers_must_close(self, db):
        task = await create_issue(title="Patient")
        first = await create_issue(title="First")
        second = await create_issue(title="Second")
        await add_dependency(task["id"], first["id"], dep_type="blocks")
        await add_dependency(task["id"], second["id"], dep_type="blocks")

        await close_issue(first["id"], actor="ana")
        assert "Patient" not in titles(await get_ready_work())

        await close_issue(second["id"], actor="ana")
        assert "Patient" in titles(await get_ready_work())

    async def test_child_of_open_epic_is_ready(self, db):
        """parent-child groups work; it does not sequence it."""
        epic = await create_issue(title="Epic", issue_type="epic")
        await create_child_issue(epic["id"], title="Child task")

        assert "Child task" in titles(await get_ready_work())

    async def test_epics_are_excluded_by_default(self, db):
        await create_issue(title="Container", issue_type="epic")

        assert titles(await get_ready_work()) == set()
        assert "Container" in titles(await get_ready_work(include_epics=True))

    async def test_in_progress_work_is_not_offered_again(self, db):
        issue = await create_issue(title="Underway")
        await claim_issue(issue["id"], actor="ana", assignee="ana")

        assert "Underway" not in titles(await get_ready_work())

    async def test_can_filter_to_one_assignee(self, db):
        mine = await create_issue(title="Mine", assignee="ana")
        await create_issue(title="Theirs", assignee="bo")
        assert mine["assignee"] == "ana"

        assert titles(await get_ready_work(assignee="ana")) == {"Mine"}

    async def test_most_urgent_comes_first(self, db):
        await create_issue(title="Low", priority=4)
        await create_issue(title="Urgent", priority=0)
        await create_issue(title="Middling", priority=2)

        result = await get_ready_work()
        assert [i["title"] for i in result["issues"]] == [
            "Urgent",
            "Middling",
            "Low",
        ]

    async def test_pinned_outranks_priority(self, db):
        await create_issue(title="Urgent", priority=0)
        await create_issue(title="Pinned", priority=4, pinned=True)

        result = await get_ready_work()
        assert result["issues"][0]["title"] == "Pinned"

    async def test_limit_must_be_positive(self, db):
        with pytest.raises(ValidationError, match="positive integer"):
            await get_ready_work(limit=0)


class TestBlockedIssues:
    async def test_reports_what_is_blocking(self, db):
        task = await create_issue(title="Stuck")
        blocker = await create_issue(title="Culprit")
        await add_dependency(task["id"], blocker["id"], dep_type="blocks")

        result = await get_blocked_issues()

        assert result["count"] == 1
        entry = result["issues"][0]
        assert entry["title"] == "Stuck"
        assert [b["title"] for b in entry["blocked_by"]] == ["Culprit"]

    async def test_closed_blockers_are_not_listed(self, db):
        task = await create_issue(title="Freed")
        blocker = await create_issue(title="Gone")
        await add_dependency(task["id"], blocker["id"], dep_type="blocks")
        await close_issue(blocker["id"], actor="ana")

        assert (await get_blocked_issues())["count"] == 0


class TestListIssues:
    async def test_closed_issues_are_hidden_by_default(self, db):
        keep = await create_issue(title="Open one")
        gone = await create_issue(title="Closed one")
        await close_issue(gone["id"], actor="ana")
        assert keep["status"] == "open"

        assert titles(await list_issues()) == {"Open one"}
        assert "Closed one" in titles(await list_issues(include_closed=True))

    async def test_filter_by_status(self, db):
        issue = await create_issue(title="Working")
        await claim_issue(issue["id"], actor="ana", assignee="ana")
        await create_issue(title="Waiting")

        assert titles(await list_issues(status="in_progress")) == {"Working"}

    async def test_unknown_status_filter_is_rejected(self, db):
        with pytest.raises(ValidationError):
            await list_issues(status="nearly-done")

    async def test_priority_max_is_inclusive(self, db):
        await create_issue(title="P0", priority=0)
        await create_issue(title="P1", priority=1)
        await create_issue(title="P3", priority=3)

        assert titles(await list_issues(priority_max=1)) == {"P0", "P1"}

    async def test_search_covers_title_and_description(self, db):
        await create_issue(title="Parser rewrite")
        await create_issue(title="Unrelated", description="mentions the parser")
        await create_issue(title="Nothing to see")

        assert titles(await list_issues(search="parser")) == {
            "Parser rewrite",
            "Unrelated",
        }

    async def test_search_is_case_insensitive(self, db):
        await create_issue(title="Parser rewrite")
        assert titles(await list_issues(search="PARSER")) == {"Parser rewrite"}

    async def test_label_filter_requires_all_labels(self, db):
        both = await create_issue(title="Both", labels=["backend", "urgent"])
        await create_issue(title="One", labels=["backend"])
        assert both["title"] == "Both"

        assert titles(await list_issues(labels=["backend", "urgent"])) == {"Both"}

    async def test_total_reflects_matches_before_paging(self, db):
        for n in range(5):
            await create_issue(title=f"Issue {n}")

        page = await list_issues(limit=2)

        assert page["total"] == 5
        assert page["count"] == 2

    async def test_offset_walks_the_result_set(self, db):
        for n in range(3):
            await create_issue(title=f"Issue {n}", priority=n)

        first = await list_issues(limit=1, offset=0)
        second = await list_issues(limit=1, offset=1)

        assert first["issues"][0]["title"] != second["issues"][0]["title"]

    async def test_negative_offset_is_rejected(self, db):
        with pytest.raises(ValidationError, match="non-negative"):
            await list_issues(offset=-1)

    async def test_limit_is_capped(self, db):
        await create_issue(title="Only one")
        assert (await list_issues(limit=10_000))["limit"] == 500


class TestLabels:
    async def test_labels_are_deduplicated_and_trimmed(self, db):
        issue = await create_issue(title="Tagged", labels=["  api ", "api", "db"])

        details = await get_issue_details(issue["id"])
        assert sorted(details["labels"]) == ["api", "db"]

    async def test_bare_string_is_rejected(self, db):
        """ "backend" would otherwise be iterated into seven single-character labels."""
        issue = await create_issue(title="Careful")
        with pytest.raises(ValidationError, match="not a single string"):
            await add_labels(issue["id"], "backend")

    async def test_remove_returns_a_count(self, db):
        issue = await create_issue(title="Tagged", labels=["a", "b"])

        assert await remove_labels(issue["id"], ["a", "missing"]) == 1

    async def test_set_labels_replaces_the_set(self, db):
        issue = await create_issue(title="Tagged", labels=["old"])

        await set_labels(issue["id"], ["new", "newer"])

        details = await get_issue_details(issue["id"])
        assert sorted(details["labels"]) == ["new", "newer"]

    async def test_set_labels_can_clear(self, db):
        issue = await create_issue(title="Tagged", labels=["temporary"])
        await set_labels(issue["id"], [])

        assert (await get_issue_details(issue["id"]))["labels"] == []

    async def test_relabelling_the_same_label_is_harmless(self, db):
        issue = await create_issue(title="Tagged", labels=["keep"])
        await add_labels(issue["id"], ["keep"])

        assert (await get_issue_details(issue["id"]))["labels"] == ["keep"]


class TestStats:
    async def test_counts_reflect_the_board(self, db):
        await create_issue(title="Ready one")
        blocked = await create_issue(title="Blocked one")
        blocker = await create_issue(title="Blocker")
        await add_dependency(blocked["id"], blocker["id"], dep_type="blocks")
        done = await create_issue(title="Done")
        await close_issue(done["id"], actor="ana")

        stats = await get_issue_stats()

        assert stats["total"] == 4
        assert stats["closed"] == 1
        assert stats["blocked"] == 1
        assert stats["ready"] == 2  # "Ready one" and "Blocker"

    async def test_empty_board_is_all_zeroes(self, db):
        stats = await get_issue_stats()

        assert stats["total"] == 0
        assert stats["ready"] == 0
        assert stats["blocked"] == 0
