"""Shared dataclasses for service layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class MovieData:
    """Structured movie metadata used for D-Day creation."""

    title: str
    release_date: date
    overview: str | None = None
    distributor: str | None = None
    director: str | None = None
    cast: list[str] | None = None
    genre: list[str] | None = None
    poster_url: str | None = None
    source: str | None = None
    external_id: str | None = None
    is_re_release: bool = False

    def cast_as_string(self) -> str | None:
        return ", ".join(self.cast) if self.cast else None

    def genre_as_string(self) -> str | None:
        return ", ".join(self.genre) if self.genre else None
