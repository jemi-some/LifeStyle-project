import datetime as dt
import os
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import dday as dday_service
from app.services.models import MovieData


@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    # Ensure LangChain tracing flags don't pollute tests
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_PROJECT", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "")


@pytest.fixture
def sample_movie():
    return MovieData(
        title="프로젝트 헤일메리",
        release_date=dt.date(2026, 3, 18),
        overview="테스트",
        distributor="테스트 배급",
        director="테스트 감독",
        cast=["배우 A", "배우 B"],
        genre=["SF"],
        source="tmdb",
        external_id="123",
        is_re_release=False,
    )


def test_calculate_dday_label_variants():
    assert dday_service.calculate_dday_label(dt.date(2026, 3, 28), today=dt.date(2026, 3, 18)) == "D-10"
    assert dday_service.calculate_dday_label(dt.date(2026, 3, 18), today=dt.date(2026, 3, 18)) == "D-DAY"
    assert dday_service.calculate_dday_label(dt.date(2026, 3, 16), today=dt.date(2026, 3, 18)) == "D+2"


def test_build_project_params(sample_movie):
    params = dday_service.build_project_params(project_name="테스트", movie=sample_movie, today=dt.date(2026, 3, 8))
    assert params["movie_title"] == sample_movie.title
    assert params["dday_label"] == "D-10"
    assert params["cast"] == "배우 A, 배우 B"
    assert params["genre"] == "SF"


@pytest.fixture
def mock_orchestrate(monkeypatch, sample_movie):
    def _fake(query: str) -> MovieData:
        return sample_movie

    monkeypatch.setattr(dday_service, "orchestrate_movie_lookup", _fake)
    monkeypatch.setattr("app.main.orchestrate_movie_lookup", _fake)
    return _fake


@pytest.fixture
def client():
    return TestClient(app)


def test_dday_endpoint_creates_new_record(client, mock_orchestrate):
    payload = {"query": "프로젝트 헤일메리 디데이"}
    response = client.post("/dday", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == payload["query"].strip()
    assert body["movie_title"] == "프로젝트 헤일메리"
    assert body["message"].startswith("새로운 D-Day")


def test_dday_endpoint_returns_existing_record(client, mock_orchestrate):
    payload = {"query": "프로젝트 헤일메리 디데이"}
    first = client.post("/dday", json=payload)
    assert first.status_code == 200
    second = client.post("/dday", json=payload)
    assert second.status_code == 200
    assert "이미 등록된" in second.json()["message"]


def test_orchestrate_movie_lookup_without_openai(monkeypatch, sample_movie):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with mock.patch("app.services.tmdb.TMDbClient.search_movie", return_value=sample_movie) as search_mock:
        movie = dday_service.orchestrate_movie_lookup("프로젝트 헤일메리")
        assert movie.title == sample_movie.title
        assert search_mock.called
