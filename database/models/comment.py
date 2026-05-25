"""Comment model (maps to table `con_mcp_comments`)."""

from __future__ import annotations


from sqlalchemy import Column, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from .__utils__ import Base, TimestampMixin


class Comment(Base, TimestampMixin):
    __tablename__ = "con_mcp_comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    issue_id = Column(
        Integer,
        ForeignKey("con_mcp_issues.id", ondelete="CASCADE"),
        nullable=False,
    )
    author = Column(String, nullable=False)
    text = Column(Text, nullable=False)

    __table_args__ = (
        Index("idx_con_mcp_comments_issue", "issue_id"),
        Index("idx_con_mcp_comments_created_at", "created_at"),
    )

    issue = relationship("Issue", back_populates="comments")
