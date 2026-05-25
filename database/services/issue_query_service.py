"""Query helpers (Beads-like "show" / IssueDetails retrieval).

In Beads (Go), `bd show` typically returns an IssueDetails structure:
- Issue fields
- Labels (list[str])
- Dependencies (list of issues + dependency_type metadata)
- Dependents (reverse edges)
- Comments
- Parent (single parent id via parent-child edge, if any)

The schema design is graph-first:
- hierarchy is Dependency(type='parent-child') from child -> parent

This module provides Python equivalents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from ..db_client import auto_session
from ..models import Comment, Dependency, Issue, Label


@dataclass(frozen=True)
class IssueWithDependencyMetadata:
    """Like internal/types.IssueWithDependencyMetadata in Go."""

    issue: Issue
    dependency_type: str


@dataclass(frozen=True)
class IssueDetails:
    """Like internal/types.IssueDetails in Go."""

    issue: Issue
    labels: list[str]
    dependencies: list[IssueWithDependencyMetadata]
    dependents: list[IssueWithDependencyMetadata]
    comments: list[Comment]
    parent: int | None


async def get_issue_details(
    issue_id: int, include_nested_deps: bool = True
) -> dict[str, Any]:
    """Return IssueDetails for a given issue id.

    This is the DB-only equivalent of what `bd show <id>` needs.

    What you get:
    - Issue row
    - Labels (strings)
    - Dependencies: list of (Issue, dependency_type) for outgoing edges
    - Dependents: list of (Issue, dependency_type) for incoming edges
    - Comments
    - Parent: the depends_on_id of the *parent-child* edge (if present)

    Args:
        issue_id: The ID of the issue to get details for
        include_nested_deps: If True, include dependency info for each dependent/dependency

    Notes:
    - Beads expects parent-child to usually be a single parent, but the schema allows multiple.
      Here we pick the first one ordered by depends_on_id.
    """
    async with auto_session() as session:
        issue = await session.get(Issue, issue_id)
        if issue is None:
            raise ValueError(f"issue not found: {issue_id}")

        # Labels
        result = await session.execute(
            select(Label.label).where(Label.issue_id == issue_id)
        )
        labels = list(result.scalars())

        # Comments
        result = await session.execute(
            select(Comment)
            .where(Comment.issue_id == issue_id)
            .order_by(Comment.created_at)
        )
        comments = list(result.scalars())

        # Parent (via parent-child edge: child(issue_id) -> parent(depends_on_id))
        result = await session.execute(
            select(Dependency.depends_on_id)
            .where(Dependency.issue_id == issue_id, Dependency.type == "parent-child")
            .order_by(Dependency.depends_on_id)
            .limit(1)
        )
        parent = result.scalar()

        # Outgoing dependencies (dependencies)
        result = await session.execute(
            select(Dependency).where(Dependency.issue_id == issue_id)
        )
        dep_rows = list(result.scalars())
        dependencies: list[IssueWithDependencyMetadata] = []
        if dep_rows:
            dep_target_ids = [d.depends_on_id for d in dep_rows]
            result = await session.execute(
                select(Issue).where(Issue.id.in_(dep_target_ids))
            )
            targets = {i.id: i for i in result.scalars()}
            for d in dep_rows:
                tgt = targets.get(d.depends_on_id)
                if tgt is None:
                    # should not happen with FK, but keep robust
                    continue
                dependencies.append(
                    IssueWithDependencyMetadata(issue=tgt, dependency_type=d.type)
                )

        # Incoming dependencies (dependents)
        result = await session.execute(
            select(Dependency).where(Dependency.depends_on_id == issue_id)
        )
        incoming_rows = list(result.scalars())
        dependents: list[IssueWithDependencyMetadata] = []
        if incoming_rows:
            src_ids = [d.issue_id for d in incoming_rows]
            result = await session.execute(select(Issue).where(Issue.id.in_(src_ids)))
            sources = {i.id: i for i in result.scalars()}
            for d in incoming_rows:
                src = sources.get(d.issue_id)
                if src is None:
                    continue
                dependents.append(
                    IssueWithDependencyMetadata(issue=src, dependency_type=d.type)
                )

        # If requested, fetch nested dependency info for all dependents and dependencies
        nested_deps_map: dict[int, dict[str, Any]] = {}
        if include_nested_deps:
            all_related_ids = [d.issue.id for d in dependencies] + [
                d.issue.id for d in dependents
            ]
            if all_related_ids:
                # Fetch all dependencies for related issues
                result = await session.execute(
                    select(Dependency).where(Dependency.issue_id.in_(all_related_ids))
                )
                outgoing = list(result.scalars())

                # Fetch all dependents for related issues
                result = await session.execute(
                    select(Dependency).where(
                        Dependency.depends_on_id.in_(all_related_ids)
                    )
                )
                incoming = list(result.scalars())

                # Collect all issue IDs we need to fetch
                all_dep_issue_ids = set()
                for dep in outgoing:
                    all_dep_issue_ids.add(dep.depends_on_id)
                for dep in incoming:
                    all_dep_issue_ids.add(dep.issue_id)

                # Fetch all issues in one query
                issue_map: dict[int, Issue] = {}
                if all_dep_issue_ids:
                    result = await session.execute(
                        select(Issue).where(Issue.id.in_(all_dep_issue_ids))
                    )
                    issue_map = {i.id: i for i in result.scalars()}

                # Build the nested dependency map
                for related_id in all_related_ids:
                    related_deps = [d for d in outgoing if d.issue_id == related_id]
                    related_incoming = [
                        d for d in incoming if d.depends_on_id == related_id
                    ]

                    nested_deps_map[related_id] = {
                        "dependencies": [
                            {
                                "id": d.depends_on_id,
                                "title": issue_map[d.depends_on_id].title
                                if d.depends_on_id in issue_map
                                else None,
                                "dependency_type": d.type,
                            }
                            for d in related_deps
                        ],
                        "dependents": [
                            {
                                "id": d.issue_id,
                                "title": issue_map[d.issue_id].title
                                if d.issue_id in issue_map
                                else None,
                                "dependency_type": d.type,
                            }
                            for d in related_incoming
                        ],
                    }

        details = IssueDetails(
            issue=issue,
            labels=labels,
            dependencies=dependencies,
            dependents=dependents,
            comments=comments,
            parent=parent,
        )

        return issue_details_to_dict(details, nested_deps_map)


def issue_details_to_dict(
    details: IssueDetails, nested_deps_map: dict[int, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Convert IssueDetails to a JSON-serializable dict.

    Useful if you want to match `bd show --json` style output.

    Args:
        details: The IssueDetails object to convert
        nested_deps_map: Optional map of issue_id -> {dependencies, dependents} for nested info

    Note:
    - The Issue ORM object contains datetime fields; if you need strict JSON, serialize datetimes
      (e.g. `.isoformat()`). This function keeps them as-is.
    """

    def issue_to_dict(i: Issue) -> dict[str, Any]:
        return {
            "id": i.id,
            "title": i.title,
            "description": i.description,
            "acceptance_criteria": i.acceptance_criteria,
            "notes": i.notes,
            "status": i.status,
            "priority": i.priority,
            "issue_type": i.issue_type,
            "assignee": i.assignee,
            "estimated_minutes": i.estimated_minutes,
            "created_at": i.created_at,
            "created_by": i.created_by,
            "updated_at": i.updated_at,
            "pinned": i.pinned,
        }

    # Build dependencies list with optional nested info
    dependencies_list = []
    for d in details.dependencies:
        dep_dict = {**issue_to_dict(d.issue), "dependency_type": d.dependency_type}
        if nested_deps_map and d.issue.id in nested_deps_map:
            dep_dict.update(nested_deps_map[d.issue.id])
        dependencies_list.append(dep_dict)

    # Build dependents list with optional nested info
    dependents_list = []
    for d in details.dependents:
        dep_dict = {**issue_to_dict(d.issue), "dependency_type": d.dependency_type}
        if nested_deps_map and d.issue.id in nested_deps_map:
            dep_dict.update(nested_deps_map[d.issue.id])
        dependents_list.append(dep_dict)

    return {
        **issue_to_dict(details.issue),
        "labels": list(details.labels),
        "dependencies": dependencies_list,
        "dependents": dependents_list,
        "comments": [
            {
                "id": c.id,
                "issue_id": c.issue_id,
                "author": c.author,
                "text": c.text,
                "created_at": c.created_at,
            }
            for c in details.comments
        ],
        "parent": details.parent,
    }
