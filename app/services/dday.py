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
    """주어진 개봉일과 오늘 날짜를 비교해 표준 D-Day 라벨을 만든다."""

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
    """영화 메타데이터를 SQLAlchemy 모델 생성에 필요한 dict로 변환."""

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
        "content_type": movie.content_type,
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
    llm_with_tools = llm.bind_tools([_MOVIE_SEARCH_TOOL, _TV_SEARCH_TOOL])

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

    payload = _run_tool(ai_message.tool_calls)
    if payload:
        return _payload_to_movie(payload)

    logger.info("LLM response missing movie_search tool call, using direct TMDb lookup")
    return tmdb_client.search_movie(title=user_query)


logger = logging.getLogger(__name__)
_SYSTEM_PROMPT = (
    "You help users coordinate shared movie/TV release D-Days. "
    "Always normalize the title (fix missing spaces like '28년후' -> '28년 후',"
    " correct casing, prefer official Korean titles) before calling a tool."
    " If the request is about a film, call movie_search; if it's TV/드라마/시리즈,"
    " call tv_search. Always call one of these tools before answering."
)


def _movie_search_tool_func(
    title: str,
    year: int | None = None,
    country: str | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """TMDb API를 호출해 LangChain 툴 응답 포맷을 반환."""
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


def _tv_search_tool_func(
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
    return _movie_to_payload(series, content_type="tv")


_TV_SEARCH_TOOL = StructuredTool.from_function(
    func=_tv_search_tool_func,
    name="tv_search",
    description="Search TMDb for TV series metadata.",
)


def _run_tool(tool_calls: Iterable[Any]) -> dict[str, Any] | None:
    """LLM 응답의 tool_calls에서 지원하는 툴을 찾아 실행."""
    if not tool_calls:
        return None
    for call in tool_calls:
        name = getattr(call, "name", None) or call.get("name")
        if name not in {"movie_search", "tv_search"}:
            continue
        args = getattr(call, "args", None) or call.get("args") or {}
        logger.debug("LangChain tool args via LLM: %s", args)
        tool = _MOVIE_SEARCH_TOOL if name == "movie_search" else _TV_SEARCH_TOOL
        return tool.invoke(args)
    return None


def _movie_to_payload(movie: MovieData, *, content_type: str | None = None) -> dict[str, Any]:
    """MovieData 객체를 LLM 툴 응답 payload 형태로 직렬화."""
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
        "content_type": content_type or ("tv" if movie.source == "tmdb_tv" else "movie"),
    }


def _payload_to_movie(payload: dict[str, Any]) -> MovieData:
    """툴 호출 결과 dict를 MovieData 도메인 객체로 역직렬화."""
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
