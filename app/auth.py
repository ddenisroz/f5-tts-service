from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from .config import Settings, get_settings


def _extract_bearer_token(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip() or None
    return value


def verify_api_key(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    x_internal_service_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    allowed_keys = settings.api_keys
    if not allowed_keys:
        return

    token = (
        _extract_bearer_token(authorization)
        or _extract_bearer_token(x_api_key)
        or _extract_bearer_token(x_internal_service_key)
    )
    if token and token in allowed_keys:
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
    )
