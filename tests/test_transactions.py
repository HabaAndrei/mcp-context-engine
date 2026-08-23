"""Session handling, atomicity and cascade behaviour."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from database.db_client import auto_session, get_session, session_scope
from database.models import Comment, Dependency, Event, Issue, Label
from database.services import (
    add_comment,
    add_dependency,
    create_issue,
    delete_issue,
    get_issue_details,
    list_issues,
)


class TestAmbientSession:
    async def test_no_session_outside_a_scope(self, db):
        assert get_session() is None

    async def test_scope_publishes_a_session(self, db):
        async with session_scope() as session:
            assert get_session() is session

    async def test_scope_is_cleared_afterwards(self, db):
        async with session_scope():
            pass
        assert get_session() is None

    async def test_nested_calls_join_the_outer_session(self, db):
        async with session_scope() as outer:
            async with auto_session() as inner:
                assert inner is outer

    async def test_several_writes_commit_together(self, db):
        async with session_scope():
            issue = await create_issue(title="Grouped")
            await add_comment(issue["id"], author="ana", text="in the same unit")

        details = await get_issue_details(issue["id"])
        assert len(details["comments"]) == 1

    async def test_a_failure_rolls_the_whole_group_back(self, db):
        with pytest.raises(RuntimeError):
            async with session_scope():
                await create_issue(title="Doomed")
                raise RuntimeError("something went wrong downstream")

        assert (await list_issues(include_closed=True))["total"] == 0


class TestCascades:
    async def test_deleting_an_issue_removes_its_children_rows(self, db):
        """SQLite ignores foreign keys unless each connection opts in.

        Without the PRAGMA the declared ON DELETE CASCADE is inert and these
        rows would be orphaned rather than removed.
        """
        issue = await create_issue(title="Doomed", labels=["temp"])
        other = await create_issue(title="Survivor")
        await add_comment(issue["id"], author="ana", text="goodbye")
        await add_dependency(issue["id"], other["id"], dep_type="related")

        doomed_id = issue["id"]
        assert await delete_issue(doomed_id) is True

        async with auto_session() as session:
            # Scoped to the deleted issue: the surviving issue keeps its own
            # rows, including the event recording its creation.
            for model in (Label, Comment, Event, Dependency):
                remaining = await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.issue_id == doomed_id)
                )
                assert remaining == 0, f"{model.__name__} rows were orphaned"

            # The edge pointed at the survivor; it must go with the source too.
            inbound = await session.scalar(
                select(func.count())
                .select_from(Dependency)
                .where(Dependency.depends_on_id == doomed_id)
            )
            assert inbound == 0

            survivors = await session.scalar(select(func.count()).select_from(Issue))
            assert survivors == 1

    async def test_deleting_a_missing_issue_reports_false(self, db):
        assert await delete_issue(4242) is False
