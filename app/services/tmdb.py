"""Thin wrapper around the TMDb API to fetch movie/TV metadata."""

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
    is_upcoming: bool = True


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
        print("[TMDb] search results:", payload)
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
        print("[TMDb] details:", details)
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
            is_upcoming=release.is_upcoming,
        )

    def _select_candidate(
        self, results: Iterable[dict[str, Any]], *, date_field: str = "release_date"
    ) -> dict[str, Any]:
        today = date.today()
        future = []
        fallback = []
        for item in results:
            rd = self._parse_date(item.get(date_field))
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

    def search_tv(
        self,
        *,
        title: str,
        first_air_date_year: int | None = None,
        language: str | None = None,
        region: str | None = None,
    ) -> MovieData:
        """Search TMDb for TV series metadata."""

        payload = self._request(
            "GET",
            "/search/tv",
            params={
                "query": title,
                "include_adult": False,
                "language": language or self.default_language,
                "first_air_date_year": first_air_date_year,
                "region": region or self.default_region,
            },
        )
        results = payload.get("results", [])
        logger.debug("TMDb TV search payload: %s", payload)
        print("[TMDb TV] search results:", payload)
        if not results:
            raise TMDbNotFound(f"TMDb TV search returned no results for '{title}'")

        # Fetch details for top 5 candidates to find any with an upcoming episode.
        candidate = None
        details = None
        today = date.today()
        
        for item in results[:5]:
            item_details = self._request(
                "GET",
                f"/tv/{item['id']}",
                params={
                    "language": language or self.default_language,
                    "append_to_response": "credits",
                },
            )
            print(f"[TMDb TV] details ({item.get('name')}):", item_details)
            next_episode = item_details.get("next_episode_to_air")
            if next_episode and next_episode.get("air_date"):
                parsed = self._parse_date(next_episode.get("air_date"))
                if parsed and parsed >= today:
                    candidate = item
                    details = item_details
                    break

        if not candidate:
            # Fallback: return the most recently aired show
            fallback_item = self._select_candidate(results, date_field="first_air_date")
            fallback_details = self._request(
                "GET",
                f"/tv/{fallback_item['id']}",
                params={
                    "language": language or self.default_language,
                    "append_to_response": "credits",
                },
            )
            release_raw = fallback_details.get("last_air_date") or fallback_details.get("first_air_date")
            release = self._parse_date(release_raw) or date.today()
            return MovieData(
                title=fallback_details.get("name") or title,
                release_date=release,
                overview=fallback_details.get("overview"),
                distributor=self._extract_network(fallback_details),
                director=None,
                cast=self._extract_cast(fallback_details.get("credits", {})),
                genre=[g["name"] for g in fallback_details.get("genres", [])],
                poster_url=self._build_poster_url(
                    fallback_details.get("poster_path") or fallback_item.get("poster_path")
                ),
                source="tmdb_tv",
                external_id=str(fallback_details.get("id")),
                is_re_release=False,
                is_upcoming=False,
            )

        logger.debug("TMDb TV details payload: %s", details)
        
        # Next episode to air
        next_episode = details.get("next_episode_to_air")
        if next_episode and next_episode.get("air_date"):
            release_raw = next_episode.get("air_date")
        else:
            release_raw = details.get("first_air_date") # fallback to satisfy typing, but we know it's future

        release = self._parse_date(release_raw)
        if not release:
            release = date.today()
            
        return MovieData(
            title=details.get("name") or title,
            release_date=release,
            overview=details.get("overview"),
            distributor=self._extract_network(details),
            director=None,
            cast=self._extract_cast(details.get("credits", {})),
            genre=[g["name"] for g in details.get("genres", [])],
            poster_url=self._build_poster_url(details.get("poster_path") or candidate.get("poster_path")),
            source="tmdb_tv",
            external_id=str(details.get("id")),
            is_re_release=False,
        )

    # type 2: Limited Theatrical, type 3: Theatrical
    _THEATRICAL_TYPES: frozenset[int] = frozenset({2, 3})

    def _select_release(
        self,
        release_dates_payload: dict[str, Any],
        region: str | None,
    ) -> TMDbReleaseInfo | None:
        region_code = region or self.default_region
        today = date.today()
        preferred_future: list[TMDbReleaseInfo] = []
        fallback_future: list[TMDbReleaseInfo] = []
        preferred_past: list[TMDbReleaseInfo] = []
        fallback_past: list[TMDbReleaseInfo] = []
        for entry in release_dates_payload.get("results", []):
            is_preferred = not region_code or entry.get("iso_3166_1") == region_code
            for info in entry.get("release_dates", []):
                if info.get("type") not in self._THEATRICAL_TYPES:
                    continue
                parsed = self._parse_date(info.get("release_date"))
                if not parsed:
                    continue
                if parsed >= today:
                    (preferred_future if is_preferred else fallback_future).append(
                        TMDbReleaseInfo(parsed)
                    )
                else:
                    (preferred_past if is_preferred else fallback_past).append(
                        TMDbReleaseInfo(parsed, is_upcoming=False)
                    )
        if preferred_future:
            preferred_future.sort(key=lambda r: r.date)
            return preferred_future[0]
        if preferred_past:
            preferred_past.sort(key=lambda r: r.date, reverse=True)
            return preferred_past[0]
        if fallback_future:
            fallback_future.sort(key=lambda r: r.date)
            return fallback_future[0]
        # Fallback: most recent past theatrical release from any region
        if fallback_past:
            fallback_past.sort(key=lambda r: r.date, reverse=True)
            return fallback_past[0]
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
    def _extract_network(details: dict[str, Any]) -> str | None:
        networks = details.get("networks") or []
        if not networks:
            return None
        return ", ".join(net["name"] for net in networks)

    @staticmethod
    def _extract_cast(credits: dict[str, Any], *, limit: int = 5) -> list[str] | None:
        cast = credits.get("cast") or []
        names = [person.get("name") for person in cast if person.get("name")]
        return names[:limit] if names else None

    def _build_poster_url(self, path: str | None) -> str | None:
        if not path:
            return None
        return f"{self.image_base}{path}"
