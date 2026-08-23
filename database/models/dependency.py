"""Dependency model (maps to table `con_mcp_dependencies`).

This is the key edge table:
- parent-child hierarchy uses type='parent-child' (child -> parent)
- blocking uses type='blocks'
- other relationships are also encoded via `type`.
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Index, JSON, String, Integer
from sqlalchemy.orm import relationship

from .__utils__ import Base, TimestampMixin


class Dependency(Base, TimestampMixin):
    __tablename__ = "con_mcp_dependencies"

    issue_id = Column(
        Integer,
        ForeignKey("con_mcp_issues.id", ondelete="CASCADE"),
        primary_key=True,
    )
    depends_on_id = Column(
        Integer,
        ForeignKey("con_mcp_issues.id", ondelete="CASCADE"),
        primary_key=True,
    )

    type = Column(String, nullable=False, default="blocks")
    created_by = Column(String, nullable=False)

    # Using metadata_ because 'metadata' is reserved by SQLAlchemy Base class
    metadata_ = Column("metadata", JSON, nullable=False, default=dict)

    thread_id = Column(String, nullable=False, default="")

    __table_args__ = (
        Index("idx_con_mcp_dependencies_issue", "issue_id"),
        Index("idx_con_mcp_dependencies_depends_on", "depends_on_id"),
        Index("idx_con_mcp_dependencies_depends_on_type", "depends_on_id", "type"),
        Index(
            "idx_con_mcp_dependencies_depends_on_type_issue",
            "depends_on_id",
            "type",
            "issue_id",
        ),
    )

    issue = relationship(
        "Issue",
        foreign_keys=[issue_id],
        back_populates="outgoing_dependencies",
    )

    depends_on = relationship(
        "Issue",
        foreign_keys=[depends_on_id],
        back_populates="incoming_dependencies",
    )
