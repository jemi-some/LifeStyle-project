"""Authentication dependencies for validating Supabase JWTs."""

from __future__ import annotations

import logging
from typing import Mapping, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

logger = logging.getLogger(__name__)

try:
    import cryptography
    logger.info("Cryptography library is available")
except ImportError:
    logger.warning("Cryptography library NOT found. Asymmetric JWT (ES256/RS256) will fail.")

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
        header = jwt.get_unverified_header(credentials.credentials)
        alg = header.get("alg")

        if alg == "HS256":
            # Traditional symmetric encryption (Legacy Secret)
            payload = jwt.decode(
                credentials.credentials,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False}
            )
        elif alg in ["RS256", "ES256"] and settings.supabase_url:
            # Modern asymmetric encryption (Signing Keys via JWKS)
            jwks_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/jwks"
            jwks_client = jwt.PyJWKClient(jwks_url)
            signing_key = jwks_client.get_signing_key_from_jwt(credentials.credentials)
            
            payload = jwt.decode(
                credentials.credentials,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                options={"verify_aud": False}
            )
        else:
            # Fallback/Error if algorithm is unsupported or URL missing
            payload = jwt.decode(
                credentials.credentials,
                settings.supabase_jwt_secret,
                algorithms=["HS256", "RS256", "ES256"],
                options={"verify_aud": False}
            )
            
        return payload

    except jwt.ExpiredSignatureError as exc:
        logger.warning(f"JWT validation failed: Token expired. Detail: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except Exception as exc:
        # Debug: check the header for all other errors
        try:
            header = jwt.get_unverified_header(credentials.credentials)
            logger.warning(f"JWT Header: {header}")
            reason = f"{exc} (Header: {header})"
        except Exception:
            reason = str(exc)
            
        logger.warning(f"JWT validation failed: Invalid token. Reason: {reason}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {reason}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc



