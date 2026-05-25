"""Event model (maps to table `con_mcp_events`).

This is a per-issue audit trail of field changes / actions.
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from .__utils__ import Base, TimestampMixin


class Event(Base, TimestampMixin):
    __tablename__ = "con_mcp_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    issue_id = Column(
        Integer,
        ForeignKey("con_mcp_issues.id", ondelete="CASCADE"),
        nullable=False,
    )

    event_type = Column(String, nullable=False)
    actor = Column(String, nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    comment = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_con_mcp_events_issue", "issue_id"),
        Index("idx_con_mcp_events_created_at", "created_at"),
    )

    issue = relationship("Issue", back_populates="events")
