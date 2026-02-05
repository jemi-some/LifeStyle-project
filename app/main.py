"""FastAPI entrypoint wiring repositories and (future) LLM orchestration."""

from __future__ import annotations

from datetime import date

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.langchain_config import configure_langchain_env
from app.db import ProjectRepository, get_session, init_models
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
        return DDayResponse(
            name=existing.name,
            movie_title=existing.movie_title,
            release_date=existing.release_date,
            dday=existing.dday_label,
            shared=True,
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

    params = build_project_params(project_name=normalized_name, movie=movie)
    record = repo.create(session, **params)
    return DDayResponse(
        name=record.name,
        movie_title=record.movie_title,
        release_date=record.release_date,
        dday=record.dday_label,
        shared=True,
        message="새로운 D-Day를 기록했습니다.",
    )
