"""Tool registry for chat orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from langchain_core.tools import StructuredTool

from app.core.config import get_settings
from app.services.tmdb import TMDbClient


def _movie_search_tool(
    title: str,
    year: int | None = None,
    country: str | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    tmdb_client = TMDbClient()
    movie = tmdb_client.search_movie(
        title=title,
        year=year,
        region=country or settings.tmdb_region,
        language=language or settings.tmdb_language,
    )
    return {
        "title": movie.title,
        "release_date": movie.release_date.isoformat(),
        "overview": movie.overview,
        "distributor": movie.distributor,
        "director": movie.director,
        "cast": movie.cast or [],
        "genre": movie.genre or [],
        "poster_url": movie.poster_url,
        "source": movie.source,
        "external_id": movie.external_id,
        "is_re_release": movie.is_re_release,
    }


@dataclass(frozen=True)
class ToolSpec:
    name: str
    tool: StructuredTool
    result_type: str


_MOVIE_TOOL = ToolSpec(
    name="movie_search",
    tool=StructuredTool.from_function(
        func=_movie_search_tool,
        name="movie_search",
        description="Search TMDb for movie release metadata.",
    ),
    result_type="movie",
)


def get_tool_specs() -> list[ToolSpec]:
    """Return all available tool specifications."""

    return [_MOVIE_TOOL]
