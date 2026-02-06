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
        "content_type": "movie",
    }


def _tv_search_tool(
    title: str,
    first_air_date_year: int | None = None,
    country: str | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    tmdb_client = TMDbClient()
    series = tmdb_client.search_tv(
        title=title,
        first_air_date_year=first_air_date_year,
        region=country or settings.tmdb_region,
        language=language or settings.tmdb_language,
    )
    return {
        "title": series.title,
        "release_date": series.release_date.isoformat(),
        "overview": series.overview,
        "distributor": series.distributor,
        "director": series.director,
        "cast": series.cast or [],
        "genre": series.genre or [],
        "poster_url": series.poster_url,
        "source": series.source,
        "external_id": series.external_id,
        "is_re_release": series.is_re_release,
        "content_type": "tv",
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

_TV_TOOL = ToolSpec(
    name="tv_search",
    tool=StructuredTool.from_function(
        func=_tv_search_tool,
        name="tv_search",
        description="Search TMDb for TV series metadata.",
    ),
    result_type="tv",
)


def get_tool_specs() -> list[ToolSpec]:
    """Return all available tool specifications."""

    return [_MOVIE_TOOL, _TV_TOOL]
