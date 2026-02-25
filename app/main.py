"""FastAPI entrypoint wiring repositories and (future) LLM orchestration."""

from __future__ import annotations

import json
from datetime import date
from typing import Mapping, Any

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import dataclasses

from app.core.langchain_config import configure_langchain_env
from app.core.auth import get_current_user
from app.db import DDayRepository, get_session, init_models
from app.models import Movie, UserDDay
from app.services.chat_orchestrator import run_chat_orchestrator_events
from app.services.dday import orchestrate_movie_lookup
from app.services.models import MovieData
from app.services.tmdb import TMDbNoUpcomingRelease, TMDbNotFound, TMDbError

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Configure LangChain + ensure database tables before serving."""

    configure_langchain_env()
    init_models()
    yield


app = FastAPI(title="D-Day Service", lifespan=lifespan)
repo = DDayRepository()


class DDayRequest(BaseModel):
    query: str = Field(..., description="원하는 프로젝트/영화명과 액션을 담은 문장")


class DDayResponse(BaseModel):
    name: str
    movie_title: str
    release_date: date
    dday: str
    waiting_count: int = 1
    message: str | None = None
    poster_url: str | None = None
    distributor: str | None = None
    director: str | None = None
    cast: list[str] | None = None
    genre: list[str] | None = None
    content_type: str = "movie"


class LongestDDayResponse(BaseModel):
    movie_title: str
    release_date: date
    dday: str


class ChatRequest(BaseModel):
    query: str = Field(..., description="일반 대화/툴 요청 문장")


class MovieConfirmRequest(BaseModel):
    query_name: str
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
    content_type: str = "movie"


def _sse_event(event: str, payload: dict | None = None) -> str:
    data = json.dumps(payload or {}, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"


@app.post("/dday", response_model=DDayResponse)
def upsert_dday(
    payload: DDayRequest,
    session: Session = Depends(get_session),
    user: Mapping[str, Any] = Depends(get_current_user),
) -> DDayResponse:
    """Fetch an existing shared D-Day or create a new one via the LLM flow."""
    user_id = user["sub"]
    normalized_name = payload.query.strip()
    if not normalized_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="query must not be empty",
        )

    try:
        movie_data = orchestrate_movie_lookup(payload.query)
    except TMDbNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="영화를 찾지 못했습니다. 제목이나 연도를 다시 알려주세요.",
        ) from exc
    except TMDbNoUpcomingRelease as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="예정된 개봉/방영일이 없어 D-Day를 만들 수 없어요.",
        ) from exc
    except TMDbError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="영화 정보를 불러오는 중 문제가 발생했습니다.",
        ) from exc

    existing_movie = repo.get_movie_by_source_and_id(
        session,
        source=movie_data.source,
        external_id=movie_data.external_id,
    )
    
    if existing_movie:
        existing_dday = repo.get_user_dday(session, user_id, existing_movie.id)
        if existing_dday:
            return _dday_to_response(
                session, existing_movie, existing_dday, 
                message="이미 서로 기다리고 있는 작품입니다!"
            )
    else:
        existing_movie = repo.create_movie(
            session,
            title=movie_data.title,
            distributor=movie_data.distributor,
            release_date=movie_data.release_date,
            director=movie_data.director,
            cast=movie_data.cast_as_string(),
            genre=movie_data.genre_as_string(),
            poster_url=movie_data.poster_url,
            source=movie_data.source,
            external_id=movie_data.external_id,
            is_re_release=movie_data.is_re_release,
            content_type=movie_data.content_type,
        )

    user_dday = repo.create_user_dday(
        session,
        user_id=user_id,
        movie_id=existing_movie.id,
        query_name=normalized_name,
        dday_label=_compute_dday(existing_movie.release_date),
    )
    return _dday_to_response(
        session, existing_movie, user_dday, message="새로운 D-Day를 기록했습니다."
    )


@app.post("/dday/confirm", response_model=DDayResponse)
def confirm_dday(
    payload: MovieConfirmRequest,
    session: Session = Depends(get_session),
    user: Mapping[str, Any] = Depends(get_current_user),
) -> DDayResponse:
    """Confirm and save a movie D-Day after user approves the preview."""
    user_id = user["sub"]
    
    existing_movie = repo.get_movie_by_source_and_id(
        session, source=payload.source, external_id=payload.external_id
    )
    if not existing_movie:
        existing_movie = repo.create_movie(
            session,
            title=payload.title,
            distributor=payload.distributor,
            release_date=payload.release_date,
            director=payload.director,
            cast=",".join(payload.cast) if payload.cast else None,
            genre=",".join(payload.genre) if payload.genre else None,
            poster_url=payload.poster_url,
            source=payload.source,
            external_id=payload.external_id,
            is_re_release=payload.is_re_release,
            content_type=payload.content_type,
        )
        
    existing_dday = repo.get_user_dday(session, user_id, existing_movie.id)
    if existing_dday:
        return _dday_to_response(
            session, existing_movie, existing_dday,
            message="이미 등록된 개봉일입니다. 모두 함께 기다리고 있어요.",
        )
        
    user_dday = repo.create_user_dday(
        session,
        user_id=user_id,
        movie_id=existing_movie.id,
        query_name=payload.query_name,
        dday_label=_compute_dday(existing_movie.release_date),
    )
    return _dday_to_response(
        session, existing_movie, user_dday,
        message="새로운 D-Day를 기록했습니다.",
    )

@app.get("/dday", response_model=list[DDayResponse])
def list_user_ddays(
    session: Session = Depends(get_session),
    user: Mapping[str, Any] = Depends(get_current_user),
) -> list[DDayResponse]:
    """List D-Days for the currently authenticated user."""
    user_id = user["sub"]
    records = repo.list_user_ddays(session, user_id)
    return [_dday_to_response(session, movie, dday) for dday, movie in records]


@app.get("/dday/longest", response_model=LongestDDayResponse | None)
def get_longest_dday(
    session: Session = Depends(get_session),
    user: Mapping[str, Any] = Depends(get_current_user),
) -> LongestDDayResponse | None:
    user_id = user["sub"]
    records = repo.list_user_ddays(session, user_id)
    today = date.today()
    candidates: list[tuple[UserDDay, Movie, int]] = []
    for dday, movie in records:
        delta = (movie.release_date - today).days
        if delta >= 0:
            candidates.append((dday, movie, delta))
    if not candidates:
        return None
    _, movie, _ = max(candidates, key=lambda item: item[2])
    return LongestDDayResponse(
        movie_title=movie.title,
        release_date=movie.release_date,
        dday=_compute_dday(movie.release_date),
    )


@app.post("/chat/stream")
async def stream_chat(
    payload: ChatRequest,
    session: Session = Depends(get_session),
    user: Mapping[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    user_id = user["sub"]
    normalized = payload.query.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="query must not be empty",
        )

    async def event_stream():
        yield _sse_event("start", {"message": "대화를 시작합니다."})
        try:
            handled_final = False
            async for event in run_chat_orchestrator_events(payload.query):
                etype = event.get("type")
                if etype == "analysis":
                    yield _sse_event("analysis", {"message": event.get("message", "요청을 분석 중입니다.")})
                elif etype == "tool_started":
                    yield _sse_event(
                        "tool_started",
                        {"message": event.get("message", "TMDB에서 개봉 정보를 찾는 중...")},
                    )
                elif etype in {"movie", "tv"}:
                    movie = event["movie"]
                    
                    # See if this movie already exists globally
                    existing_movie = repo.get_movie_by_source_and_id(
                        session,
                        source=movie.source,
                        external_id=movie.external_id,
                    )
                    
                    yield _sse_event(
                        "tool_result",
                        {
                            "message": event.get("message", f"{movie.title} 정보를 찾았어요."),
                            "title": movie.title,
                            "release_date": movie.release_date.isoformat(),
                            "content_type": getattr(movie, "content_type", "movie"),
                        },
                    )
                    
                    has_dday = False
                    if existing_movie:
                        existing_dday = repo.get_user_dday(session, user_id, existing_movie.id)
                        if existing_dday:
                            response = _dday_to_response(
                                session, existing_movie, existing_dday,
                                message="이미 등록된 디데이입니다. 관련 새로운 소식은 연동 준비 중입니다.",
                            )
                            yield _sse_event("dday", response.model_dump(mode="json"))
                            has_dday = True
                            
                    if not has_dday:
                        movie_dict = dataclasses.asdict(movie)
                        movie_dict["release_date"] = movie.release_date.isoformat()
                        confirm_payload = {
                            "query_name": normalized,
                            **movie_dict
                        }
                        # Retrieve waiting count globally
                        if existing_movie:
                            waiting_count = repo.count_waiting_users(session, existing_movie.id)
                            confirm_payload["waiting_count"] = waiting_count
                        else:
                            confirm_payload["waiting_count"] = 0
                            
                        yield _sse_event("confirmation_required", confirm_payload)
                        
                elif etype == "token":
                    message = event.get("message")
                    if message:
                        yield _sse_event("token", {"message": message})
                elif etype == "final":
                    final_message = event.get("message") or "어떤 영화를 기다리고 싶은지 알려주세요."
                    yield _sse_event("assistant_message", {"message": final_message})
                    handled_final = True
                    break
            if not handled_final:
                fallback = "어떤 영화를 기다리고 싶은지 알려주세요."
                yield _sse_event("token", {"message": fallback})
                yield _sse_event("assistant_message", {"message": fallback})
        except TMDbNotFound:
            yield _sse_event(
                "assistant_message",
                {"message": "영화를 찾지 못했습니다. 제목이나 연도를 다시 알려주세요."},
            )
        except TMDbNoUpcomingRelease:
            yield _sse_event(
                "assistant_message",
                {"message": "예정된 개봉/방영일이 없어 D-Day를 만들 수 없어요."},
            )
        except TMDbError:
            yield _sse_event(
                "error",
                {"message": "영화 정보를 불러오는 중 문제가 발생했습니다."},
            )
        except Exception as exc:  # pragma: no cover
            yield _sse_event("error", {"message": f"예상치 못한 오류가 발생했습니다: {exc}"})
        finally:
            yield _sse_event("end")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _dday_to_response(
    session: Session, movie: Movie, user_dday: UserDDay, *, message: str | None = None
) -> DDayResponse:
    waiting_count = repo.count_waiting_users(session, movie.id)
    return DDayResponse(
        name=user_dday.query_name,
        movie_title=movie.title,
        release_date=movie.release_date,
        dday=_compute_dday(movie.release_date),
        waiting_count=waiting_count,
        message=message,
        poster_url=movie.poster_url,
        distributor=movie.distributor,
        director=movie.director,
        cast=_split_list_field(movie.cast),
        genre=_split_list_field(movie.genre),
        content_type=getattr(movie, "content_type", "movie"),
    )


def _split_list_field(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    values = [chunk.strip() for chunk in raw.split(",") if chunk.strip()]
    return values or None


def _compute_dday(release_date: date) -> str:
    today = date.today()
    delta = (release_date - today).days
    if delta > 0:
        return f"D-{delta}"
    if delta == 0:
        return "D-DAY"
    return f"D+{abs(delta)}"


def _format_dday_sentence(movie_title: str, release_date: date, dday: str) -> str:
    return f"{movie_title}은 {release_date.isoformat()} 개봉 예정이라 {dday}입니다."
