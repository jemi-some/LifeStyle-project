"""Authentication dependencies – verify Supabase token via Supabase API."""

from __future__ import annotations

import logging
from typing import Mapping, Any

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

logger = logging.getLogger(__name__)

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Mapping[str, Any]:
    """Verify the Supabase JWT by asking Supabase directly."""
    settings = get_settings()

    # Dev fallback when Supabase is not configured
    if not settings.supabase_url:
        logger.warning("VITE_SUPABASE_URL not configured. Using dummy user for dev.")
        return {"sub": "developer-user-123", "email": "dev@example.com"}

    # Ask Supabase: "Is this token valid? Who is this user?"
    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/user"
    headers = {
        "Authorization": f"Bearer {credentials.credentials}",
        "apikey": settings.supabase_anon_key or "",
    }

    try:
        response = httpx.get(url, headers=headers, timeout=10)
    except httpx.RequestError as exc:
        logger.error(f"Failed to reach Supabase: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to verify authentication with Supabase",
        ) from exc

    if response.status_code != 200:
        logger.warning(f"Supabase auth rejected token: {response.status_code} {response.text[:200]}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_data = response.json()
    # Return a dict compatible with the rest of our code (needs "sub" key)
    return {
        "sub": user_data.get("id", ""),
        "email": user_data.get("email", ""),
        **user_data,
    }
