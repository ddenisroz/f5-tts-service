from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, status

from .config import Settings, get_settings

def _matches_api_key(token: str, allowed_keys: set[str]) -> bool:
    return any(hmac.compare_digest(token, allowed) for allowed in allowed_keys)


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
    settings: Settings = Depends(get_settings),
) -> None:
    token = _extract_bearer_token(authorization) or _extract_bearer_token(x_api_key)
    allowed_keys = settings.api_keys
    if token and _matches_api_key(token, allowed_keys):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
    )
