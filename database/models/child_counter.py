"""ChildCounter model (maps to table `con_mcp_child_counters`).

Tracks sequential child numbers per parent issue (hierarchical ID generation helper).
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer
from sqlalchemy.orm import relationship

from .__utils__ import Base


class ChildCounter(Base):
    __tablename__ = "con_mcp_child_counters"

    parent_id = Column(
        Integer,
        ForeignKey("con_mcp_issues.id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_child = Column(Integer, nullable=False, default=0)

    parent = relationship("Issue")
