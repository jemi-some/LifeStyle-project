"""Thin wrapper around the TMDb API to fetch movie metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable

import logging

import httpx

from app.core.config import get_settings
from app.services.models import MovieData


logger = logging.getLogger(__name__)


class TMDbError(Exception):
    """Base exception for TMDb-related failures."""


class TMDbNotFound(TMDbError):
    """Raised when TMDb cannot find a movie for the given query."""


class TMDbNoUpcomingRelease(TMDbError):
    """Raised when no future or re-release dates exist for a movie."""


@dataclass
class TMDbReleaseInfo:
    date: date
    is_re_release: bool = False


class TMDbClient:
    """Simple TMDb HTTP client using API key auth."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        default_language: str | None = None,
        default_region: str | None = None,
        image_base: str | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.tmdb_api_key
        self.base_url = base_url or settings.tmdb_base_url.rstrip("/")
        self.default_language = default_language or settings.tmdb_language
        self.default_region = default_region or settings.tmdb_region
        self.image_base = image_base or settings.tmdb_image_base.rstrip("/")
        self.timeout = 10.0

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None) -> Any:
        if not self.api_key:
            raise TMDbError("TMDB_API_KEY is not configured")
        url = f"{self.base_url}{path}"
        query = {"api_key": self.api_key}
        if params:
            query.update({k: v for k, v in params.items() if v is not None})
        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(method, url, params=query)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:  # pragma: no cover - network failure
                raise TMDbError(str(exc)) from exc
        return response.json()

    def search_movie(
        self,
        *,
        title: str,
        year: int | None = None,
        language: str | None = None,
        region: str | None = None,
    ) -> MovieData:
        """Search TMDb for a movie and return structured metadata."""

        payload = self._request(
            "GET",
            "/search/movie",
            params={
                "query": title,
                "include_adult": False,
                "language": language or self.default_language,
                "year": year,
                "region": region or self.default_region,
            },
        )
        results = payload.get("results", [])
        logger.debug("TMDb search payload: %s", payload)
        if not results:
            raise TMDbNotFound(f"TMDb search returned no results for '{title}'")

        # Choose the most relevant candidate by release date proximity.
        candidate = self._select_candidate(results)
        details = self._request(
            "GET",
            f"/movie/{candidate['id']}",
            params={
                "language": language or self.default_language,
                "append_to_response": "credits,release_dates",
            },
        )
        logger.debug("TMDb details payload: %s", details)
        release = self._select_release(details.get("release_dates", {}), region)
        if release is None:
            raise TMDbNoUpcomingRelease(
                "No upcoming or re-release dates available for this movie"
            )
        return MovieData(
            title=details.get("title") or candidate.get("title") or title,
            release_date=release.date,
            overview=details.get("overview"),
            distributor=self._extract_distributor(details),
            director=self._extract_director(details.get("credits", {})),
            cast=self._extract_cast(details.get("credits", {})),
            genre=[g["name"] for g in details.get("genres", [])],
            poster_url=self._build_poster_url(details.get("poster_path") or candidate.get("poster_path")),
            source="tmdb",
            external_id=str(details.get("id")),
            is_re_release=release.is_re_release,
        )

    def _select_candidate(self, results: Iterable[dict[str, Any]]) -> dict[str, Any]:
        today = date.today()
        future = []
        fallback = []
        for item in results:
            rd = self._parse_date(item.get("release_date"))
            if not rd:
                continue
            if rd >= today:
                future.append((rd, item))
            else:
                fallback.append((rd, item))
        if future:
            future.sort(key=lambda pair: pair[0])
            return future[0][1]
        if fallback:
            fallback.sort(key=lambda pair: pair[0], reverse=True)
            return fallback[0][1]
        # If all records miss release dates, just return the first entry.
        return next(iter(results))

    def _select_release(
        self,
        release_dates_payload: dict[str, Any],
        region: str | None,
    ) -> TMDbReleaseInfo | None:
        region_code = region or self.default_region
        today = date.today()
        preferred_future: list[TMDbReleaseInfo] = []
        preferred_re_release: list[TMDbReleaseInfo] = []
        fallback_future: list[TMDbReleaseInfo] = []
        fallback_re_release: list[TMDbReleaseInfo] = []
        for entry in release_dates_payload.get("results", []):
            is_preferred = not region_code or entry.get("iso_3166_1") == region_code
            for info in entry.get("release_dates", []):
                parsed = self._parse_date(info.get("release_date"))
                if not parsed:
                    continue
                is_re = info.get("type") == 5  # 5 => re-release per TMDb docs
                buckets = (
                    (preferred_re_release if is_re else preferred_future)
                    if is_preferred
                    else (fallback_re_release if is_re else fallback_future)
                )
                if parsed >= today:
                    buckets.append(TMDbReleaseInfo(parsed, is_re))
        for collection in (preferred_future, preferred_re_release, fallback_future, fallback_re_release):
            if collection:
                collection.sort(key=lambda r: r.date)
                return collection[0]
        return None

    @staticmethod
    def _parse_date(raw: str | None) -> date | None:
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw[:10]).date()
        except ValueError:
            return None

    @staticmethod
    def _extract_distributor(details: dict[str, Any]) -> str | None:
        companies = details.get("production_companies") or []
        if not companies:
            return None
        return ", ".join(company["name"] for company in companies)

    @staticmethod
    def _extract_director(credits: dict[str, Any]) -> str | None:
        crew = credits.get("crew") or []
        for member in crew:
            if member.get("job") == "Director" and member.get("name"):
                return member["name"]
        return None

    @staticmethod
    def _extract_cast(credits: dict[str, Any], *, limit: int = 5) -> list[str] | None:
        cast = credits.get("cast") or []
        names = [person.get("name") for person in cast if person.get("name")]
        return names[:limit] if names else None

    def _build_poster_url(self, path: str | None) -> str | None:
        if not path:
            return None
        return f"{self.image_base}{path}"
