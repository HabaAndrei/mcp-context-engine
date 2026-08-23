"""ORM row -> plain dict conversion.

Service functions used to return `instance.__dict__`, which exposes
SQLAlchemy's private `_sa_instance_state`, omits attributes that happen not to
be loaded yet, and yields raw `datetime` objects that are not JSON
serialisable. Every field emitted here is chosen deliberately, and timestamps
are rendered as ISO-8601 strings so results survive a `json.dumps` unchanged.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import Comment, Dependency, Event, Issue


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def issue_to_dict(issue: Issue) -> dict[str, Any]:
    """Render an issue as a JSON-safe dict."""
    return {
        "id": issue.id,
        "title": issue.title,
        "description": issue.description,
        "acceptance_criteria": issue.acceptance_criteria,
        "notes": issue.notes,
        "status": issue.status,
        "priority": issue.priority,
        "issue_type": issue.issue_type,
        "assignee": issue.assignee,
        "estimated_minutes": issue.estimated_minutes,
        "created_by": issue.created_by,
        "pinned": issue.pinned,
        "created_at": _isoformat(issue.created_at),
        "updated_at": _isoformat(issue.updated_at),
    }


def issue_summary(issue: Issue) -> dict[str, Any]:
    """Render the subset of fields useful when listing many issues.

    List and graph responses can span hundreds of rows; sending full
    descriptions for each wastes the agent's context window, which is the very
    resource this server exists to protect.
    """
    return {
        "id": issue.id,
        "title": issue.title,
        "status": issue.status,
        "priority": issue.priority,
        "issue_type": issue.issue_type,
        "assignee": issue.assignee,
    }


def comment_to_dict(comment: Comment) -> dict[str, Any]:
    return {
        "id": comment.id,
        "issue_id": comment.issue_id,
        "author": comment.author,
        "text": comment.text,
        "created_at": _isoformat(comment.created_at),
    }


def event_to_dict(event: Event) -> dict[str, Any]:
    return {
        "id": event.id,
        "issue_id": event.issue_id,
        "event_type": event.event_type,
        "actor": event.actor,
        "old_value": event.old_value,
        "new_value": event.new_value,
        "comment": event.comment,
        "created_at": _isoformat(event.created_at),
    }


def dependency_to_dict(dependency: Dependency) -> dict[str, Any]:
    return {
        "issue_id": dependency.issue_id,
        "depends_on_id": dependency.depends_on_id,
        "type": dependency.type,
        "created_by": dependency.created_by,
        "metadata": dependency.metadata_ or {},
        "thread_id": dependency.thread_id,
        "created_at": _isoformat(dependency.created_at),
    }
