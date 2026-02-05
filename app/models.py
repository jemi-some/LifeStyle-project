"""SQLAlchemy ORM models.

This module defines the "projects" table which stores the shared D-Day
records. Keeping it isolated here makes future Alembic migrations simpler.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Project(Base):
    """Represents a movie/project entry that everyone can wait for together."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    movie_title: Mapped[str] = mapped_column(String(255))
    distributor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    release_date: Mapped[date] = mapped_column(Date, index=True)
    director: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cast: Mapped[str | None] = mapped_column(Text, nullable=True)
    genre: Mapped[str | None] = mapped_column(String(255), nullable=True)
    poster_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    dday_label: Mapped[str] = mapped_column(String(32))
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(128))
    is_re_release: Mapped[bool] = mapped_column(Boolean, default=False)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_projects_source_external"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"Project(id={self.id}, name={self.name}, release_date={self.release_date})"
