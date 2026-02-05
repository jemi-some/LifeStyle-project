"""Service helpers for D-Day orchestration."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Iterable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.services.models import MovieData
from app.services.tmdb import TMDbClient


def calculate_dday_label(release_date: date, *, today: date | None = None) -> str:
    """Return the canonical D-Day label (D-10/D-DAY/D+5)."""

    today = today or date.today()
    delta = (release_date - today).days
    if delta > 0:
        return f"D-{delta}"
    if delta == 0:
        return "D-DAY"
    return f"D+{abs(delta)}"


def build_project_params(
    *, project_name: str, movie: MovieData, today: date | None = None
) -> dict:
    """Create kwargs for ProjectRepository.create from movie data."""

    return {
        "name": project_name,
        "movie_title": movie.title,
        "distributor": movie.distributor,
        "release_date": movie.release_date,
        "director": movie.director,
        "cast": movie.cast_as_string(),
        "genre": movie.genre_as_string(),
        "poster_url": movie.poster_url,
        "dday_label": calculate_dday_label(movie.release_date, today=today),
        "source": movie.source,
        "external_id": movie.external_id,
        "is_re_release": movie.is_re_release,
    }


def orchestrate_movie_lookup(user_query: str) -> MovieData:
    """Use LangChain (ChatOpenAI + StructuredTool) to fetch movie metadata."""

    settings = get_settings()
    tmdb_client = TMDbClient()

    if not settings.openai_api_key:
        return tmdb_client.search_movie(title=user_query)

    llm = ChatOpenAI(
        temperature=0.0,
        model=settings.openai_model,
        api_key=settings.openai_api_key,
    )
    llm_with_tools = llm.bind_tools([_MOVIE_SEARCH_TOOL])

    try:
        ai_message = llm_with_tools.invoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=user_query),
            ]
        )
    except Exception as exc:  # pragma: no cover - network failure
        logger.warning("LangChain/OpenAI call failed, fallback to TMDb direct: %s", exc)
        return tmdb_client.search_movie(title=user_query)

    payload = _run_movie_search_tool(ai_message.tool_calls)
    if payload:
        return _payload_to_movie(payload)

    logger.info("LLM response missing movie_search tool call, using direct TMDb lookup")
    return tmdb_client.search_movie(title=user_query)


logger = logging.getLogger(__name__)
_SYSTEM_PROMPT = (
    "You help users coordinate shared movie release D-Days. "
    "Always normalize the movie title (fix missing spaces like '28년후' -> '28년 후',"
    " correct casing, prefer official Korean titles) before calling the movie_search"
    " tool, and always call that tool before answering."
)


def _movie_search_tool_func(
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
    return _movie_to_payload(movie)


_MOVIE_SEARCH_TOOL = StructuredTool.from_function(
    func=_movie_search_tool_func,
    name="movie_search",
    description="Search TMDb for a movie release date and metadata.",
)


def _run_movie_search_tool(tool_calls: Iterable[Any]) -> dict[str, Any] | None:
    if not tool_calls:
        return None
    for call in tool_calls:
        name = getattr(call, "name", None) or call.get("name")
        if name != "movie_search":
            continue
        args = getattr(call, "args", None) or call.get("args") or {}
        logger.debug("movie_search tool args via LangChain: %s", args)
        return _MOVIE_SEARCH_TOOL.invoke(args)
    return None


def _movie_to_payload(movie: MovieData) -> dict[str, Any]:
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


def _payload_to_movie(payload: dict[str, Any]) -> MovieData:
    raw_release = payload.get("release_date")
    if isinstance(raw_release, date):
        release_date = raw_release
    else:
        release_date = datetime.fromisoformat(str(raw_release)).date()
    cast = payload.get("cast") or None
    genre = payload.get("genre") or None
    return MovieData(
        title=payload.get("title", ""),
        release_date=release_date,
        overview=payload.get("overview"),
        distributor=payload.get("distributor"),
        director=payload.get("director"),
        cast=cast,
        genre=genre,
        poster_url=payload.get("poster_url"),
        source=payload.get("source"),
        external_id=payload.get("external_id"),
        is_re_release=bool(payload.get("is_re_release", False)),
    )
