"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    tmdb_api_key: str | None = Field(default=None, alias="TMDB_API_KEY")
    tmdb_base_url: str = Field(default="https://api.themoviedb.org/3")
    tmdb_language: str = Field(default="ko-KR")
    tmdb_region: str | None = Field(default="KR")
    tmdb_image_base: str = Field(default="https://image.tmdb.org/t/p/w500")
    langchain_tracing_v2: bool = Field(default=False, alias="LANGCHAIN_TRACING_V2")
    langchain_api_key: str | None = Field(default=None, alias="LANGCHAIN_API_KEY")
    langchain_project: str | None = Field(default=None, alias="LANGCHAIN_PROJECT")
    database_url: str = Field(default="sqlite:///./dday.db", alias="DATABASE_URL")
    supabase_url: str | None = Field(default=None, alias="VITE_SUPABASE_URL")
    supabase_anon_key: str | None = Field(default=None, alias="VITE_SUPABASE_ANON_KEY")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")



@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()
