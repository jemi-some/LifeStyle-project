"""Authentication dependencies for validating Supabase JWTs."""

from __future__ import annotations

import logging
from typing import Mapping, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

logger = logging.getLogger(__name__)

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Mapping[str, Any]:
    """Verify the Supabase JWT token and return the payload."""
    settings = get_settings()

    if not settings.supabase_jwt_secret:
        # Fallback for dev environments if secret is missing
        logger.warning("SUPABASE_JWT_SECRET not configured. Using dummy user for dev.")
        return {"sub": "developer-user-123", "email": "dev@example.com"}

    try:
        # Supabase uses HS256 algorithm by default
        payload = jwt.decode(
            credentials.credentials,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError as exc:
        logger.warning(f"JWT validation failed: Token expired. Detail: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        logger.warning(f"JWT validation failed: Invalid token. Reason: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

