"""Utilities to configure LangChain/LangSmith from environment settings."""

from __future__ import annotations

import os

from app.core.config import get_settings


def configure_langchain_env() -> None:
    """Set optional LangSmith env vars if provided in settings."""

    settings = get_settings()
    if settings.langchain_tracing_v2:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    if settings.langchain_api_key:
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.langchain_api_key)
    if settings.langchain_project:
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.langchain_project)
