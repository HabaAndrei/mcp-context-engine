"""Issue model (maps to table `con_mcp_issues`).

Beads design note:
- Epic/task/subtask are all `Issue` rows; differentiate using Issue.issue_type.
- Hierarchy uses Dependency edges with type='parent-child' (child -> parent).
"""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Column, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from .__utils__ import Base, TimestampMixin


class Issue(Base, TimestampMixin):
    __tablename__ = "con_mcp_issues"

    id = Column(Integer, primary_key=True, autoincrement=True)

    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False, default="")
    acceptance_criteria = Column(Text, nullable=False, default="")
    notes = Column(Text, nullable=False, default="")

    status = Column(String, nullable=False, default="open")
    priority = Column(Integer, nullable=False, default=2)
    issue_type = Column(String, nullable=False, default="task")

    assignee = Column(String, nullable=True)
    estimated_minutes = Column(Integer, nullable=True)

    created_by = Column(String, nullable=False, default="")

    # Pinning for important issues
    pinned = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        CheckConstraint("length(title) <= 500", name="ck_con_mcp_issues_title_len"),
        CheckConstraint("priority >= 0 AND priority <= 4", name="ck_con_mcp_issues_priority_range"),
        Index("idx_con_mcp_issues_status", "status"),
        Index("idx_con_mcp_issues_priority", "priority"),
        Index("idx_con_mcp_issues_assignee", "assignee"),
        Index("idx_con_mcp_issues_created_at", "created_at"),
    )

    # Relationships declared by string name to avoid circular imports.
    labels = relationship(
        "Label",
        back_populates="issue",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    comments = relationship(
        "Comment",
        back_populates="issue",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    events = relationship(
        "Event",
        back_populates="issue",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    outgoing_dependencies = relationship(
        "Dependency",
        foreign_keys="Dependency.issue_id",
        back_populates="issue",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    incoming_dependencies = relationship(
        "Dependency",
        foreign_keys="Dependency.depends_on_id",
        back_populates="depends_on",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Convenience edge lists for hierarchy
    parent_edges = relationship(
        "Dependency",
        primaryjoin="and_(Issue.id==Dependency.issue_id, Dependency.type=='parent-child')",
        viewonly=True,
    )

    child_edges = relationship(
        "Dependency",
        primaryjoin="and_(Issue.id==Dependency.depends_on_id, Dependency.type=='parent-child')",
        viewonly=True,
    )
