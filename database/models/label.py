"""Label model (maps to table `con_mcp_labels`)."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Index, String, Integer
from sqlalchemy.orm import relationship

from .__utils__ import Base


class Label(Base):
    __tablename__ = "con_mcp_labels"

    issue_id = Column(
        Integer,
        ForeignKey("con_mcp_issues.id", ondelete="CASCADE"),
        primary_key=True,
    )
    label = Column(String, primary_key=True)

    __table_args__ = (
        Index("idx_con_mcp_labels_label", "label"),
    )

    issue = relationship("Issue", back_populates="labels")
