"""Authentication dependencies for the F5_tts service."""

import logging
import os
import secrets
from typing import Any, Dict, Optional, Set

import jwt
from dotenv import load_dotenv
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

load_dotenv()

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


def _internal_jwt_secret() -> Optional[str]:
    return os.getenv("INTERNAL_SERVICE_JWT_SECRET") or os.getenv("SECRET_KEY")


def _internal_jwt_audience() -> str:
    return os.getenv("INTERNAL_SERVICE_JWT_AUDIENCE", "f5_tts")


def _internal_jwt_issuer() -> str:
    return os.getenv("INTERNAL_SERVICE_JWT_ISSUER", "bot_service")


def _internal_jwt_allowed_subjects() -> Set[str]:
    raw = os.getenv("INTERNAL_SERVICE_JWT_ALLOWED_SUBJECTS", "bot_service")
    return {item.strip() for item in raw.split(",") if item.strip()}


def _verify_internal_service_jwt(token: str) -> Optional[Dict[str, Any]]:
    """Validate service JWT used for internal bot_service -> F5_tts calls."""
    signing_key = _internal_jwt_secret()
    if not token or not signing_key:
        return None

    algorithm = os.getenv("ALGORITHM", "HS256")
    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=[algorithm],
            audience=_internal_jwt_audience(),
            issuer=_internal_jwt_issuer(),
            options={
                "verify_exp": True,
                "verify_iat": True,
                "verify_nbf": True,
            },
        )
    except jwt.InvalidTokenError:
        return None

    token_type = payload.get("type") or payload.get("token_type")
    if token_type != "service":
        return None

    subject = str(payload.get("sub") or payload.get("service") or "").strip()
    if not subject:
        return None

    allowed_subjects = _internal_jwt_allowed_subjects()
    if allowed_subjects and subject not in allowed_subjects:
        logger.warning("Rejected internal service JWT subject: %s", subject)
        return None

    return {
        "user_id": 0,
        "is_admin": True,
        "service": subject,
        "auth": "service_jwt",
    }


class TTSAuthManager:
    """Authentication manager for user JWT tokens."""

    def __init__(self):
        self.secret_key = os.getenv("SECRET_KEY")
        if not self.secret_key:
            raise ValueError("SECRET_KEY environment variable is required")
        self.algorithm = os.getenv("ALGORITHM", "HS256")

    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify JWT token and return payload."""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_nbf": True,
                },
            )
            return payload
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
            ) from exc
        except jwt.InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            ) from exc

    def get_current_user(self, credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
        """Decode and validate user JWT token."""
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization required",
            )

        payload = self.verify_token(credentials.credentials)
        if "user_id" not in payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user_id",
            )

        return payload


# Global auth manager instance
auth_manager = TTSAuthManager()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """Dependency: require valid user JWT."""
    if credentials is not None:
        return auth_manager.get_current_user(credentials)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authorization required",
    )


def get_current_user_or_internal(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_internal_service_key: Optional[str] = Header(None, alias="X-Internal-Service-Key"),
) -> Dict[str, Any]:
    """Allow user JWT, service JWT, or legacy internal key."""
    if credentials is not None:
        service_user = _verify_internal_service_jwt(credentials.credentials)
        if service_user is not None:
            return service_user

        try:
            return auth_manager.get_current_user(credentials)
        except HTTPException:
            # Fall through to legacy key/development fallback for backward compatibility.
            pass

    expected_key = os.getenv("TTS_INTERNAL_API_KEY")
    if expected_key and x_internal_service_key and secrets.compare_digest(x_internal_service_key, expected_key):
        return {"user_id": 0, "is_admin": True, "service": "bot_service", "auth": "legacy_internal_key"}

    environment = (os.getenv("ENVIRONMENT") or os.getenv("ENV") or "development").lower()
    is_dev_env = environment in {"development", "dev", "testing", "test", "local"}
    if (
        not expected_key
        and is_dev_env
        and request.client
        and request.client.host in {"127.0.0.1", "::1", "localhost"}
    ):
        logger.warning(
            "Using loopback internal auth fallback in %s because TTS_INTERNAL_API_KEY is not configured",
            environment,
        )
        return {"user_id": 0, "is_admin": True, "service": "loopback", "auth": "loopback_fallback"}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authorization required",
    )


# Dependency for admin access
def get_admin_user(current_user: Dict[str, Any] = Depends(get_current_user_or_internal)) -> Dict[str, Any]:
    """Dependency: require admin role."""
    if not current_user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
