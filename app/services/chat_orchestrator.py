"""Orchestrate chat + tool interactions for the /chat endpoint."""

# 이 모듈은 LangChain ChatOpenAI 스트리밍으로 분석-툴 호출-최종 답변을 한 번에 처리한다.

from __future__ import annotations

from datetime import datetime
from typing import Any, AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.services.dday import calculate_dday_label
from app.services.models import MovieData
from app.services.tmdb import TMDbClient
from app.services.tool_registry import ToolSpec, get_tool_specs

_SYSTEM_PROMPT = (
    "You are WAITWITH, a helpful agent for shared movie D-Day tracking. "
    "Call tools such as `movie_search` only when the user clearly asks about a film"
    " release or D-Day. Otherwise, engage in small talk without tools."
)

TOOL_SPECS: list[ToolSpec] = get_tool_specs()
TOOL_MAP = {spec.name: spec for spec in TOOL_SPECS}

def build_llm_with_tools(*, streaming: bool = False) -> ChatOpenAI:
    settings = get_settings()
    llm = ChatOpenAI(
        temperature=0.0,
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        streaming=streaming,
    )
    tools = [spec.tool for spec in TOOL_SPECS]
    return llm.bind_tools(tools)

async def run_chat_orchestrator_events(
    user_query: str,
    *,
    tmdb_client: TMDbClient | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Single-pass LangChain streaming that yields tool and token events."""

    settings = get_settings()
    tmdb = tmdb_client or TMDbClient()
    yield {"type": "analysis", "message": "요청을 분석 중입니다."}  # 프론트 단계 표시용

    if not settings.openai_api_key:
        yield {"type": "tool_started", "message": "TMDB에서 개봉 정보를 찾는 중..."}
        movie = tmdb.search_movie(title=user_query)
        yield {
            "type": "movie",
            "movie": movie,
            "message": f"{movie.title} 정보를 찾았어요.",
        }
        final_text = _format_movie_sentence(movie)  # Offline 모드에서도 동일한 토큰/최종 이벤트 제공
        yield {"type": "token", "message": final_text}
        yield {"type": "final", "message": final_text}
        return

    llm = build_llm_with_tools(streaming=True)
    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_query)]
    tool_started = False
    collected_tokens: list[str] = []
    final_ai_message = None

    async for event in llm.astream_events(messages):  # LangChain이 토큰/툴 이벤트를 내보냄
        kind = event.get("event")
        if kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if not chunk:
                continue
            if _chunk_contains_tool_call(chunk) and not tool_started:
                tool_started = True
                yield {"type": "tool_started", "message": "TMDB에서 개봉 정보를 찾는 중..."}
            text_piece = _extract_text(chunk)
            if text_piece:
                collected_tokens.append(text_piece)
                yield {"type": "token", "message": "".join(collected_tokens)}  # 누적 텍스트로 프론트 버블 업데이트
        elif kind == "on_chat_model_end":
            final_ai_message = event.get("data", {}).get("output")
        elif kind == "on_tool_start":  # LangChain이 툴 호출 시작을 별도 이벤트로 주는 경우 대비
            yield {"type": "tool_started", "message": "TMDB에서 개봉 정보를 찾는 중..."}

    if final_ai_message is None:
        fallback = "어떤 영화를 기다리고 싶은지 알려주세요."
        yield {"type": "token", "message": fallback}
        yield {"type": "final", "message": fallback}
        return

    tool_call = _extract_tool_call(final_ai_message)
    if tool_call:
        spec, args = tool_call
        payload = spec.tool.invoke(args)
        if spec.result_type == "movie":
            movie = _payload_to_movie(payload)
            yield {
                "type": "movie",
                "movie": movie,
                "message": f"{movie.title} 정보를 찾았어요.",
            }
            final_text = _format_movie_sentence(movie)  # DB 저장 후 최종 문장 템플릿 재사용
            yield {"type": "token", "message": final_text}
            yield {"type": "final", "message": final_text}
            return

    final_text = _extract_text(final_ai_message) or "어떤 영화를 기다리고 싶은지 알려주세요."
    yield {"type": "token", "message": final_text}
    yield {"type": "final", "message": final_text}


def _chunk_contains_tool_call(chunk: Any) -> bool:
    if chunk is None:
        return False
    tool_calls = getattr(chunk, "tool_calls", None)
    if tool_calls:
        for call in tool_calls:
            if getattr(call, "name", None) or (isinstance(call, dict) and call.get("name")):
                return True
    return False


def _extract_tool_call(message: Any) -> tuple[ToolSpec, dict[str, Any]] | None:
    tool_calls = getattr(message, "tool_calls", None)
    if not tool_calls:
        return None
    for call in tool_calls:
        name = getattr(call, "name", None) or call.get("name")
        spec = TOOL_MAP.get(name)
        if not spec:
            continue
        args = getattr(call, "args", None) or call.get("args") or {}
        return spec, args
    return None

def _payload_to_movie(payload: dict[str, Any]) -> MovieData:
    raw_release = payload.get("release_date")
    release_date = (
        raw_release if isinstance(raw_release, datetime)
        else datetime.fromisoformat(str(raw_release)).date()
    )
    return MovieData(
        title=payload.get("title", ""),
        release_date=release_date,
        overview=payload.get("overview"),
        distributor=payload.get("distributor"),
        director=payload.get("director"),
        cast=payload.get("cast") or None,
        genre=payload.get("genre") or None,
        poster_url=payload.get("poster_url"),
        source=payload.get("source"),
        external_id=payload.get("external_id"),
        is_re_release=bool(payload.get("is_re_release", False)),
    )

def _extract_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for chunk in content:
            if isinstance(chunk, dict) and chunk.get("type") == "text":
                parts.append(str(chunk.get("text", "")))
        return "".join(parts)
    return str(content)


def _format_movie_sentence(movie: MovieData) -> str:
    dday_label = calculate_dday_label(movie.release_date)
    return f"{movie.title}은 {movie.release_date.isoformat()} 개봉 예정이라 {dday_label}입니다."
