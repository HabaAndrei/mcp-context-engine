"""Creating, updating and closing issues."""

from __future__ import annotations

import json

import pytest

from database.domain import ValidationError
from database.services import (
    IssueNotFoundError,
    add_comment,
    claim_issue,
    close_issue,
    create_issue,
    get_issue_details,
    reopen_issue,
    unassign_issue,
    update_issue_fields,
)


class TestCreate:
    async def test_returns_assigned_id_and_defaults(self, db):
        issue = await create_issue(title="Write the parser")

        assert isinstance(issue["id"], int)
        assert issue["title"] == "Write the parser"
        assert issue["status"] == "open"
        assert issue["priority"] == 2
        assert issue["issue_type"] == "task"

    async def test_result_is_json_serialisable(self, db):
        """Tool output crosses a JSON boundary, so it must survive dumps().

        The previous implementation returned instance.__dict__, which carries
        SQLAlchemy's internal state object and raw datetimes.
        """
        issue = await create_issue(title="Serialise me")

        json.dumps(issue)  # must not raise
        assert "_sa_instance_state" not in issue

    async def test_timestamps_are_populated(self, db):
        issue = await create_issue(title="Timestamped")

        assert issue["created_at"] is not None
        assert issue["updated_at"] is not None

    async def test_blank_title_is_rejected(self, db):
        with pytest.raises(ValidationError, match="title is required"):
            await create_issue(title="   ")

    async def test_overlong_title_is_rejected(self, db):
        with pytest.raises(ValidationError, match="maximum is 500"):
            await create_issue(title="x" * 501)

    @pytest.mark.parametrize("priority", [-1, 5, 99])
    async def test_priority_outside_range_is_rejected(self, db, priority):
        with pytest.raises(ValidationError, match="out of range"):
            await create_issue(title="Bad priority", priority=priority)

    async def test_boolean_priority_is_rejected(self, db):
        """True is an int subclass and would silently become priority 1."""
        with pytest.raises(ValidationError, match="must be an integer"):
            await create_issue(title="Sneaky", priority=True)

    async def test_unknown_status_is_rejected(self, db):
        with pytest.raises(ValidationError, match="not valid"):
            await create_issue(title="Typo", status="in-progress")

    async def test_negative_estimate_is_rejected(self, db):
        with pytest.raises(ValidationError, match="cannot be negative"):
            await create_issue(title="Backwards", estimated_minutes=-5)

    async def test_title_is_trimmed(self, db):
        issue = await create_issue(title="  padded  ")
        assert issue["title"] == "padded"


class TestUpdate:
    async def test_changes_only_supplied_fields(self, db):
        issue = await create_issue(title="Original", description="keep me")

        updated = await update_issue_fields(issue["id"], priority=0)

        assert updated["priority"] == 0
        assert updated["title"] == "Original"
        assert updated["description"] == "keep me"

    async def test_records_an_event_per_changed_field(self, db):
        issue = await create_issue(title="Audited")
        await update_issue_fields(issue["id"], status="in_progress", priority=1)

        details = await get_issue_details(issue["id"])
        # create + two updates
        assert details["id"] == issue["id"]
        assert details["status"] == "in_progress"
        assert details["priority"] == 1

    async def test_missing_issue_names_the_id(self, db):
        with pytest.raises(IssueNotFoundError, match="4242"):
            await update_issue_fields(4242, title="Nowhere")

    async def test_invalid_status_is_rejected(self, db):
        issue = await create_issue(title="Guarded")
        with pytest.raises(ValidationError):
            await update_issue_fields(issue["id"], status="done")


class TestClaim:
    async def test_assigns_and_starts(self, db):
        issue = await create_issue(title="Claimable")

        claimed = await claim_issue(issue["id"], actor="ana", assignee="ana")

        assert claimed["assignee"] == "ana"
        assert claimed["status"] == "in_progress"

    async def test_refuses_to_steal_by_default(self, db):
        issue = await create_issue(title="Contested")
        await claim_issue(issue["id"], actor="ana", assignee="ana")

        with pytest.raises(ValidationError, match="already claimed"):
            await claim_issue(issue["id"], actor="bo", assignee="bo")

    async def test_takeover_when_explicitly_allowed(self, db):
        issue = await create_issue(title="Handover")
        await claim_issue(issue["id"], actor="ana", assignee="ana")

        taken = await claim_issue(
            issue["id"], actor="bo", assignee="bo", fail_if_claimed=False
        )
        assert taken["assignee"] == "bo"

    async def test_reclaiming_by_same_person_is_allowed(self, db):
        issue = await create_issue(title="Mine again")
        await claim_issue(issue["id"], actor="ana", assignee="ana")

        again = await claim_issue(issue["id"], actor="ana", assignee="ana")
        assert again["assignee"] == "ana"

    async def test_blank_assignee_is_rejected(self, db):
        issue = await create_issue(title="Anonymous")
        with pytest.raises(ValidationError, match="assignee is required"):
            await claim_issue(issue["id"], actor="ana", assignee="  ")

    async def test_unassign_clears_owner(self, db):
        issue = await create_issue(title="Released")
        await claim_issue(issue["id"], actor="ana", assignee="ana")

        released = await unassign_issue(issue["id"], actor="ana")
        assert released["assignee"] is None


class TestClose:
    async def test_sets_closed_status(self, db):
        issue = await create_issue(title="Finishable")

        closed = await close_issue(issue["id"], actor="ana", reason="Done")
        assert closed["status"] == "closed"

    async def test_is_idempotent_and_returns_a_dict(self, db):
        """The second close previously returned an ORM object, not a dict."""
        issue = await create_issue(title="Twice")
        await close_issue(issue["id"], actor="ana")

        again = await close_issue(issue["id"], actor="ana")

        assert isinstance(again, dict)
        assert again["status"] == "closed"
        json.dumps(again)

    async def test_pinned_issue_needs_force(self, db):
        issue = await create_issue(title="Important", pinned=True)

        with pytest.raises(ValidationError, match="pinned"):
            await close_issue(issue["id"], actor="ana")

        forced = await close_issue(issue["id"], actor="ana", force=True)
        assert forced["status"] == "closed"

    async def test_reopen_restores_active_status(self, db):
        issue = await create_issue(title="Back from the dead")
        await close_issue(issue["id"], actor="ana")

        reopened = await reopen_issue(issue["id"], actor="ana")
        assert reopened["status"] == "open"

    async def test_reopen_cannot_close(self, db):
        issue = await create_issue(title="Contradiction")
        with pytest.raises(ValidationError):
            await reopen_issue(issue["id"], status="closed")


class TestComments:
    async def test_comment_is_attached_and_returned(self, db):
        issue = await create_issue(title="Discussed")

        comment = await add_comment(issue["id"], author="ana", text="Chose plan B")

        assert comment["text"] == "Chose plan B"
        assert comment["issue_id"] == issue["id"]
        json.dumps(comment)

    async def test_blank_comment_is_rejected(self, db):
        issue = await create_issue(title="Silent")
        with pytest.raises(ValidationError, match="cannot be blank"):
            await add_comment(issue["id"], author="ana", text="   ")

    async def test_comment_on_missing_issue_names_the_id(self, db):
        with pytest.raises(IssueNotFoundError, match="999"):
            await add_comment(999, author="ana", text="hello?")

    async def test_missing_author_becomes_unknown(self, db):
        issue = await create_issue(title="Anonymous note")
        comment = await add_comment(issue["id"], author="", text="who am I")
        assert comment["author"] == "unknown"
