"""The tracker's vocabulary: statuses, priorities, issue types, edge types.

These values are written into the database as plain strings and are matched by
callers, so they are the project's real contract. Validating them at the
service boundary keeps a typo (`"in-progress"`, `"P1"`) from becoming a row
that no filter will ever return.
"""

from __future__ import annotations

from typing import Final

# --- Issue status ----------------------------------------------------------

STATUS_OPEN: Final = "open"
STATUS_IN_PROGRESS: Final = "in_progress"
STATUS_BLOCKED: Final = "blocked"
STATUS_DEFERRED: Final = "deferred"
STATUS_CLOSED: Final = "closed"

ALL_STATUSES: Final = (
    STATUS_OPEN,
    STATUS_IN_PROGRESS,
    STATUS_BLOCKED,
    STATUS_DEFERRED,
    STATUS_CLOSED,
)

#: Statuses that represent work still on the table.
ACTIVE_STATUSES: Final = (
    STATUS_OPEN,
    STATUS_IN_PROGRESS,
    STATUS_BLOCKED,
    STATUS_DEFERRED,
)

# --- Dependency edge types -------------------------------------------------

DEP_BLOCKS: Final = "blocks"
DEP_PARENT_CHILD: Final = "parent-child"
DEP_RELATED: Final = "related"
DEP_DUPLICATES: Final = "duplicates"
DEP_SUPERSEDES: Final = "supersedes"

ALL_DEPENDENCY_TYPES: Final = (
    DEP_BLOCKS,
    DEP_PARENT_CHILD,
    DEP_RELATED,
    DEP_DUPLICATES,
    DEP_SUPERSEDES,
)

#: Only `blocks` gates execution. `related`/`duplicates`/`supersedes` are
#: annotations, and `parent-child` expresses containment: an epic groups its
#: children, it does not prevent them from starting.
BLOCKING_DEPENDENCY_TYPES: Final = (DEP_BLOCKS,)

# --- Issue types -----------------------------------------------------------

TYPE_TASK: Final = "task"
TYPE_SUBTASK: Final = "subtask"
TYPE_EPIC: Final = "epic"

ALL_ISSUE_TYPES: Final = (TYPE_TASK, TYPE_SUBTASK, TYPE_EPIC)

# --- Priority --------------------------------------------------------------

MIN_PRIORITY: Final = 0  # most urgent
MAX_PRIORITY: Final = 4  # least urgent
DEFAULT_PRIORITY: Final = 2

MAX_TITLE_LENGTH: Final = 500


class ValidationError(ValueError):
    """Raised when a caller supplies a value outside the tracker's vocabulary.

    Subclasses ValueError so existing `except ValueError` handlers, and the
    MCP tool wrappers, keep working unchanged.
    """


def _one_of(value: str, allowed: tuple[str, ...], field: str) -> str:
    if value not in allowed:
        raise ValidationError(
            f"{field}={value!r} is not valid. Expected one of: {', '.join(allowed)}."
        )
    return value


def validate_status(status: str) -> str:
    return _one_of(status, ALL_STATUSES, "status")


def validate_issue_type(issue_type: str) -> str:
    return _one_of(issue_type, ALL_ISSUE_TYPES, "issue_type")


def validate_dependency_type(dep_type: str) -> str:
    return _one_of(dep_type, ALL_DEPENDENCY_TYPES, "dep_type")


def validate_priority(priority: int) -> int:
    """Check priority is an int within range.

    `bool` is rejected explicitly: it is a subclass of `int`, so `True` would
    otherwise slip through and be stored as priority 1.
    """
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise ValidationError(
            f"priority must be an integer between {MIN_PRIORITY} and {MAX_PRIORITY}, "
            f"got {priority!r}."
        )
    if not MIN_PRIORITY <= priority <= MAX_PRIORITY:
        raise ValidationError(
            f"priority={priority} is out of range "
            f"({MIN_PRIORITY}=highest .. {MAX_PRIORITY}=lowest)."
        )
    return priority


def validate_title(title: str) -> str:
    """Check the title is present and within the column's length limit."""
    cleaned = (title or "").strip()
    if not cleaned:
        raise ValidationError("title is required and cannot be blank.")
    if len(cleaned) > MAX_TITLE_LENGTH:
        raise ValidationError(
            f"title is {len(cleaned)} characters; the maximum is {MAX_TITLE_LENGTH}."
        )
    return cleaned


def validate_estimated_minutes(minutes: int | None) -> int | None:
    """Check a time estimate is a non-negative integer, if supplied."""
    if minutes is None:
        return None
    if isinstance(minutes, bool) or not isinstance(minutes, int):
        raise ValidationError(
            f"estimated_minutes must be an integer or None, got {minutes!r}."
        )
    if minutes < 0:
        raise ValidationError(f"estimated_minutes cannot be negative, got {minutes}.")
    return minutes


def normalize_labels(labels: object) -> list[str]:
    """Coerce label input into a de-duplicated, order-preserving list.

    A bare string is rejected rather than iterated: `add_labels(1, "backend")`
    would otherwise silently attach five labels named `b`, `a`, `c`, `k`, `e`.
    """
    if labels is None:
        return []
    if isinstance(labels, str):
        raise ValidationError(
            "labels must be a list of strings, not a single string. "
            'Use ["backend"] rather than "backend".'
        )
    try:
        candidates = list(labels)  # type: ignore[call-overload]
    except TypeError:
        raise ValidationError(f"labels must be an iterable of strings, got {labels!r}.")

    seen: set[str] = set()
    result: list[str] = []
    for item in candidates:
        if not isinstance(item, str):
            raise ValidationError(f"label {item!r} is not a string.")
        cleaned = item.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result
