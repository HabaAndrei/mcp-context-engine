"""Config model (maps to SQLite table `con_mcp_config`).

Global key/value configuration (not linked to issues by foreign key).
"""

from __future__ import annotations

from sqlalchemy import Column, String, Text, Integer

from .__utils__ import Base


class Config(Base):
    __tablename__ = "con_mcp_config"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
