"""Dependency edges, hierarchy and cycle prevention."""

from __future__ import annotations

import pytest

from database.domain import ValidationError
from database.services import (
    DependencyCycleError,
    IssueNotFoundError,
    add_dependency,
    close_issue,
    create_child_issue,
    create_epic_with_children,
    create_issue,
    find_cycles,
    get_issue_details,
    get_issue_tree,
    remove_dependency,
)


class TestEdges:
    async def test_metadata_is_persisted(self, db):
        """Regression: `metadata` is reserved on the declarative base.

        Passing it as a keyword silently shadowed the class attribute instead
        of filling the column, so caller metadata was discarded and the column
        was written as {}.
        """
        a = await create_issue(title="A")
        b = await create_issue(title="B")

        edge = await add_dependency(
            a["id"], b["id"], metadata={"why": "shares a schema"}
        )

        assert edge["metadata"] == {"why": "shares a schema"}

    async def test_thread_id_and_creator_are_kept(self, db):
        a = await create_issue(title="A")
        b = await create_issue(title="B")

        edge = await add_dependency(
            a["id"], b["id"], created_by="ana", thread_id="thread-7"
        )

        assert edge["created_by"] == "ana"
        assert edge["thread_id"] == "thread-7"

    async def test_self_dependency_is_rejected(self, db):
        issue = await create_issue(title="Narcissus")
        with pytest.raises(ValidationError, match="cannot depend on itself"):
            await add_dependency(issue["id"], issue["id"])

    async def test_unknown_dependency_type_is_rejected(self, db):
        a = await create_issue(title="A")
        b = await create_issue(title="B")
        with pytest.raises(ValidationError, match="not valid"):
            await add_dependency(a["id"], b["id"], dep_type="sort-of-blocks")

    async def test_missing_endpoint_is_reported(self, db):
        a = await create_issue(title="A")
        with pytest.raises(IssueNotFoundError):
            await add_dependency(a["id"], 999)

    async def test_re_adding_updates_in_place(self, db):
        a = await create_issue(title="A")
        b = await create_issue(title="B")

        await add_dependency(a["id"], b["id"], dep_type="blocks")
        await add_dependency(a["id"], b["id"], dep_type="related")

        details = await get_issue_details(a["id"])
        edges = [d for d in details["dependencies"] if d["id"] == b["id"]]
        assert len(edges) == 1
        assert edges[0]["dependency_type"] == "related"

    async def test_remove_reports_whether_anything_went(self, db):
        a = await create_issue(title="A")
        b = await create_issue(title="B")
        await add_dependency(a["id"], b["id"])

        assert await remove_dependency(a["id"], b["id"]) is True
        assert await remove_dependency(a["id"], b["id"]) is False


class TestCyclePrevention:
    async def test_direct_blocks_cycle_is_refused(self, db):
        a = await create_issue(title="A")
        b = await create_issue(title="B")
        await add_dependency(a["id"], b["id"], dep_type="blocks")

        with pytest.raises(DependencyCycleError):
            await add_dependency(b["id"], a["id"], dep_type="blocks")

    async def test_transitive_blocks_cycle_is_refused(self, db):
        a = await create_issue(title="A")
        b = await create_issue(title="B")
        c = await create_issue(title="C")
        await add_dependency(a["id"], b["id"], dep_type="blocks")
        await add_dependency(b["id"], c["id"], dep_type="blocks")

        with pytest.raises(DependencyCycleError):
            await add_dependency(c["id"], a["id"], dep_type="blocks")

    async def test_parent_child_cycle_is_refused(self, db):
        parent = await create_issue(title="Parent", issue_type="epic")
        child = await create_child_issue(parent["id"], title="Child")

        with pytest.raises(DependencyCycleError):
            await add_dependency(parent["id"], child["id"], dep_type="parent-child")

    async def test_annotation_edges_may_be_mutual(self, db):
        """`related` carries no ordering, so a loop is meaningless, not wrong."""
        a = await create_issue(title="A")
        b = await create_issue(title="B")

        await add_dependency(a["id"], b["id"], dep_type="related")
        await add_dependency(b["id"], a["id"], dep_type="related")

    async def test_find_cycles_reports_none_on_clean_data(self, db):
        a = await create_issue(title="A")
        b = await create_issue(title="B")
        await add_dependency(a["id"], b["id"], dep_type="blocks")

        assert (await find_cycles())["count"] == 0


class TestHierarchy:
    async def test_child_points_at_parent(self, db):
        parent = await create_issue(title="Epic", issue_type="epic")
        child = await create_child_issue(parent["id"], title="Task")

        details = await get_issue_details(child["id"])
        assert details["parent"] == parent["id"]

    async def test_child_of_missing_parent_is_rejected(self, db):
        with pytest.raises(IssueNotFoundError):
            await create_child_issue(4242, title="Orphan")

    async def test_epic_with_children_links_everything(self, db):
        epic, children = await create_epic_with_children(
            epic_kwargs={"title": "Auth", "priority": 1},
            children_kwargs=[{"title": "Login"}, {"title": "Tokens"}],
            child_labels=["auth"],
        )

        assert epic["issue_type"] == "epic"
        assert len(children) == 2
        for child in children:
            assert (await get_issue_details(child["id"]))["parent"] == epic["id"]

    async def test_epic_creation_is_atomic(self, db):
        """A bad child must not leave a half-built epic behind."""
        from database.services import list_issues

        before = (await list_issues(include_closed=True))["total"]

        with pytest.raises(ValidationError):
            await create_epic_with_children(
                epic_kwargs={"title": "Doomed"},
                children_kwargs=[{"title": "Fine"}, {"title": ""}],
            )

        after = (await list_issues(include_closed=True))["total"]
        assert after == before

    async def test_tree_nests_descendants(self, db):
        epic, children = await create_epic_with_children(
            epic_kwargs={"title": "Root"},
            children_kwargs=[{"title": "One"}, {"title": "Two"}],
        )
        await create_child_issue(children[0]["id"], title="Grandchild")

        tree = await get_issue_tree(epic["id"])

        assert tree["descendant_count"] == 3
        assert len(tree["children"]) == 2
        deepest = [c for c in tree["children"] if c["children"]]
        assert deepest[0]["children"][0]["title"] == "Grandchild"

    async def test_tree_respects_max_depth(self, db):
        epic, children = await create_epic_with_children(
            epic_kwargs={"title": "Root"}, children_kwargs=[{"title": "One"}]
        )
        await create_child_issue(children[0]["id"], title="Grandchild")

        shallow = await get_issue_tree(epic["id"], max_depth=1)
        assert shallow["descendant_count"] == 1
        assert shallow["children"][0]["children"] == []

    async def test_tree_of_missing_issue_raises(self, db):
        with pytest.raises(ValueError, match="not found"):
            await get_issue_tree(4242)


class TestBlockedFlag:
    async def test_details_report_blocking_state(self, db):
        task = await create_issue(title="Dependent")
        blocker = await create_issue(title="Blocker")
        await add_dependency(task["id"], blocker["id"], dep_type="blocks")

        assert (await get_issue_details(task["id"]))["is_blocked"] is True

        await close_issue(blocker["id"], actor="ana")
        assert (await get_issue_details(task["id"]))["is_blocked"] is False

    async def test_parent_child_does_not_block(self, db):
        parent = await create_issue(title="Epic", issue_type="epic")
        child = await create_child_issue(parent["id"], title="Task")

        assert (await get_issue_details(child["id"]))["is_blocked"] is False
