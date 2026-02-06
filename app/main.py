"""FastAPI entrypoint wiring repositories and (future) LLM orchestration."""

from __future__ import annotations

import json
from datetime import date

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.langchain_config import configure_langchain_env
from app.db import Project, ProjectRepository, get_session, init_models
from app.services.chat_orchestrator import run_chat_orchestrator_events
from app.services.dday import build_project_params, orchestrate_movie_lookup
from app.services.tmdb import TMDbNoUpcomingRelease, TMDbNotFound, TMDbError

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Configure LangChain + ensure database tables before serving."""

    configure_langchain_env()
    init_models()
    yield


app = FastAPI(title="D-Day Service", lifespan=lifespan)
repo = ProjectRepository()


class DDayRequest(BaseModel):
    query: str = Field(..., description="원하는 프로젝트/영화명과 액션을 담은 문장")


class DDayResponse(BaseModel):
    name: str
    movie_title: str
    release_date: date
    dday: str
    shared: bool = True
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


def _sse_event(event: str, payload: dict | None = None) -> str:
    data = json.dumps(payload or {}, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"


@app.post("/dday", response_model=DDayResponse)
def upsert_dday(
    payload: DDayRequest,
    session: Session = Depends(get_session),
) -> DDayResponse:
    """Fetch an existing shared D-Day or create a new one via the LLM flow."""

    normalized_name = payload.query.strip()
    if not normalized_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="query must not be empty",
        )

    existing = repo.get_by_name(session, normalized_name)
    if existing:
        return _project_to_response(
            existing,
            message="이미 등록된 개봉일입니다. 모두 함께 기다리고 있어요.",
        )

    try:
        movie = orchestrate_movie_lookup(payload.query)
    except TMDbNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="영화를 찾지 못했습니다. 제목이나 연도를 다시 알려주세요.",
        ) from exc
    except TMDbNoUpcomingRelease as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="예정된 개봉일이 없어 D-Day를 만들 수 없어요.",
        ) from exc
    except TMDbError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="영화 정보를 불러오는 중 문제가 발생했습니다.",
        ) from exc

    existing_by_source = repo.get_by_source_and_external_id(
        session,
        source=movie.source,
        external_id=movie.external_id,
    )
    if existing_by_source:
        return _project_to_response(
            existing_by_source,
            message="이미 등록된 개봉일입니다. 모두 함께 기다리고 있어요.",
        )

    params = build_project_params(project_name=normalized_name, movie=movie)
    record = repo.create(session, **params)
    return _project_to_response(
        record,
        message="새로운 D-Day를 기록했습니다.",
    )


@app.get("/dday", response_model=list[DDayResponse])
def list_shared_ddays(session: Session = Depends(get_session)) -> list[DDayResponse]:
    records = repo.list_all(session)
    return [_project_to_response(record) for record in records]


@app.get("/dday/longest", response_model=LongestDDayResponse | None)
def get_longest_dday(session: Session = Depends(get_session)) -> LongestDDayResponse | None:
    records = repo.list_all(session)
    today = date.today()
    candidates: list[tuple[Project, int]] = []
    for project in records:
        delta = (project.release_date - today).days
        if delta >= 0:
            candidates.append((project, delta))
    if not candidates:
        return None
    project, _ = max(candidates, key=lambda item: item[1])
    return LongestDDayResponse(
        movie_title=project.movie_title,
        release_date=project.release_date,
        dday=_compute_dday(project.release_date),
    )


@app.post("/chat/stream")
async def stream_chat(
    payload: ChatRequest,
    session: Session = Depends(get_session),
) -> StreamingResponse:
    normalized = payload.query.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="query must not be empty",
        )

    async def event_stream():
        yield _sse_event("start", {"message": "대화를 시작합니다."})
        try:
            existing = repo.get_by_name(session, normalized)
            if existing:
                response = _project_to_response(
                    existing,
                    message="이미 등록된 개봉일입니다. 모두 함께 기다리고 있어요.",
                )
                yield _sse_event("dday", response.model_dump(mode="json"))
                final_message = _format_dday_sentence(
                    response.movie_title,
                    response.release_date,
                    response.dday,
                )
                yield _sse_event("token", {"message": final_message})
                yield _sse_event(
                    "assistant_message",
                    {"message": final_message},
                )
            else:
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
                        yield _sse_event(
                            "tool_result",
                            {
                                "message": event.get("message", f"{movie.title} 정보를 찾았어요."),
                                "title": movie.title,
                                "release_date": movie.release_date.isoformat(),
                                "content_type": getattr(movie, "content_type", "movie"),
                            },
                        )
                        existing_by_source = repo.get_by_source_and_external_id(
                            session,
                            source=movie.source,
                            external_id=movie.external_id,
                        )
                        if existing_by_source:
                            response = _project_to_response(
                                existing_by_source,
                                message="이미 등록된 개봉일입니다. 모두 함께 기다리고 있어요.",
                            )
                        else:
                            params = build_project_params(project_name=normalized, movie=movie)
                            record = repo.create(session, **params)
                            response = _project_to_response(
                                record,
                                message="새로운 D-Day를 기록했습니다.",
                            )
                        yield _sse_event("dday", response.model_dump(mode="json"))
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
                {"message": "예정된 개봉일이 없어 D-Day를 만들 수 없어요."},
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


def _project_to_response(project: Project, *, message: str | None = None) -> DDayResponse:
    return DDayResponse(
        name=project.name,
        movie_title=project.movie_title,
        release_date=project.release_date,
        dday=_compute_dday(project.release_date),
        shared=True,
        message=message,
        poster_url=project.poster_url,
        distributor=project.distributor,
        director=project.director,
        cast=_split_list_field(project.cast),
        genre=_split_list_field(project.genre),
        content_type=getattr(project, "content_type", "movie"),
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
