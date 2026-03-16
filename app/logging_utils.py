from __future__ import annotations

import logging
from typing import Any, Mapping

REQUEST_CONTEXT_KEYS = (
    "request_id",
    "event_id",
    "user_id",
    "channel_name",
    "author",
    "voice",
    "selected_voice",
)


def merge_request_context(*contexts: Mapping[str, Any] | None, **overrides: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for context in contexts:
        if not context:
            continue
        for key in REQUEST_CONTEXT_KEYS:
            value = context.get(key)
            if value not in (None, ""):
                merged[key] = value
    for key, value in overrides.items():
        if key in REQUEST_CONTEXT_KEYS and value not in (None, ""):
            merged[key] = value
    return merged


class RequestLoggerAdapter(logging.LoggerAdapter):
    def bind(self, **context: Any) -> "RequestLoggerAdapter":
        return RequestLoggerAdapter(self.logger, merge_request_context(self.extra, context))

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        context = merge_request_context(self.extra, kwargs.pop("request_context", None))
        prefix = _format_request_context(context)
        if prefix:
            msg = f"{prefix} {msg}"
        return msg, kwargs


def get_request_logger(base_logger: logging.Logger, context: Mapping[str, Any] | None = None) -> RequestLoggerAdapter:
    return RequestLoggerAdapter(base_logger, merge_request_context(context))


def build_request_context(
    *,
    request_id: str,
    event_id: str | None = None,
    user_id: Any = None,
    channel_name: str | None = None,
    author: str | None = None,
    voice: str | None = None,
    selected_voice: str | None = None,
) -> dict[str, Any]:
    return merge_request_context(
        {
            "request_id": request_id,
            "event_id": event_id,
            "user_id": user_id,
            "channel_name": channel_name,
            "author": author,
            "voice": voice,
            "selected_voice": selected_voice,
        }
    )


def _format_request_context(context: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in REQUEST_CONTEXT_KEYS:
        value = context.get(key)
        if value in (None, ""):
            continue
        rendered = str(value).replace('"', "'")
        parts.append(f'{key}="{rendered}"')
    if not parts:
        return ""
    return "[" + " ".join(parts) + "]"
