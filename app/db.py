"""Database session management and repositories."""

from __future__ import annotations

import os
from datetime import date
from typing import Iterator

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, Project


def _database_url() -> str:
    """Return the SQLAlchemy URL from env (defaults to local SQLite for dev)."""
    return os.getenv("DATABASE_URL", "sqlite:///./dday.db")


engine = create_engine(_database_url(), future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_models() -> None:
    """Create tables if they do not exist (handy for local dev)."""
    Base.metadata.create_all(bind=engine)


def get_session() -> Iterator[Session]:
    """FastAPI-friendly dependency that manages commits/rollbacks."""

    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class ProjectRepository:
    """High level data access helpers for shared D-Day records."""

    def get_by_name(self, session: Session, name: str) -> Project | None:
        query = select(Project).where(Project.name == name)
        return session.execute(query).scalar_one_or_none()

    def create(
        self,
        session: Session,
        *,
        name: str,
        movie_title: str,
        distributor: str | None,
        release_date: date,
        director: str | None,
        cast: str | None,
        genre: str | None,
        dday_label: str,
        source: str | None,
        external_id: str | None,
        is_re_release: bool,
    ) -> Project:
        project = Project(
            name=name,
            movie_title=movie_title,
            distributor=distributor,
            release_date=release_date,
            director=director,
            cast=cast,
            genre=genre,
            dday_label=dday_label,
            source=source,
            external_id=external_id,
            is_re_release=is_re_release,
        )
        session.add(project)
        session.flush()  # assign IDs before leaving scope
        session.refresh(project)
        return project

    def list_upcoming(self, session: Session, today: date) -> list[Project]:
        query = (
            select(Project)
            .where(Project.release_date >= today)
            .order_by(Project.release_date)
        )
        return list(session.execute(query).scalars())

    def list_all(self, session: Session) -> list[Project]:
        query = select(Project).order_by(Project.release_date)
        return list(session.execute(query).scalars())
