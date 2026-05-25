from sqlalchemy import Column, DateTime
from sqlalchemy import func
from sqlalchemy.orm import declarative_base


# Base class for all database models
Base = declarative_base()

class TimestampMixin:
    """Mixin providing automatic timestamp fields for models."""

    created_at = Column(
        DateTime,
        default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False
    )