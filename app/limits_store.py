from __future__ import annotations

import json
import os
import tempfile
from asyncio import Lock
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .limits_store_postgres import PostgresTTSLimitsStore


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_key() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _empty_usage() -> dict[str, Any]:
    return {
        "requests_count": 0,
        "total_characters": 0,
        "total_duration_sec": 0.0,
        "successful_requests": 0,
        "failed_requests": 0,
    }


class FileTTSLimitsStore:
    def __init__(
        self,
        state_path: Path,
        *,
        default_max_text_length: int,
        default_daily_limit: int,
        default_priority_level: int,
        default_tts_enabled: bool,
        retention_days: int,
    ) -> None:
        self.state_path = state_path
        self._lock = Lock()
        self.default_max_text_length = max(10, int(default_max_text_length))
        self.default_daily_limit = max(1, int(default_daily_limit))
        self.default_priority_level = max(1, int(default_priority_level))
        self.default_tts_enabled = bool(default_tts_enabled)
        self.retention_days = max(2, int(retention_days))
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            self._write_state(
                {
                    "updated_at": _utc_now_iso(),
                    "users": {},
                    "usage": {},
                }
            )

    async def startup(self) -> None:
        return

    async def close(self) -> None:
        return

    async def get_user_limits(self, user_id: int) -> dict[str, Any]:
        state = self._read_state()
        user_patch = state.get("users", {}).get(str(user_id), {})
        limits = {
            "max_text_length": self.default_max_text_length,
            "daily_limit": self.default_daily_limit,
            "priority_level": self.default_priority_level,
            "tts_enabled": self.default_tts_enabled,
        }
        limits.update({k: user_patch[k] for k in user_patch.keys() if k in limits})
        return limits

    async def update_user_limits(self, user_id: int, patch: dict[str, Any]) -> dict[str, Any]:
        sanitized = self._sanitize_limits_patch(patch)
        async with self._lock:
            state = self._read_state()
            users = state.setdefault("users", {})
            user_limits = users.setdefault(str(user_id), {})
            user_limits.update(sanitized)
            state["updated_at"] = _utc_now_iso()
            self._prune_usage(state)
            self._write_state(state)
        return await self.get_user_limits(user_id)

    async def validate_request(self, user_id: int, text: str) -> tuple[bool, str, dict[str, Any], dict[str, Any]]:
        limits = await self.get_user_limits(user_id)
        usage = await self.get_daily_usage(user_id, datetime.now(timezone.utc).date())
        text_len = len(text or "")

        if not limits["tts_enabled"]:
            return False, "TTS is disabled for this user", limits, usage
        if text_len > int(limits["max_text_length"]):
            return (
                False,
                f"Text too long. Maximum {limits['max_text_length']}, got {text_len}",
                limits,
                usage,
            )
        if int(usage["requests_count"]) >= int(limits["daily_limit"]):
            return (
                False,
                f"Daily request limit exceeded. Limit {limits['daily_limit']}, used {usage['requests_count']}",
                limits,
                usage,
            )
        return True, "Request allowed", limits, usage

    async def log_request(
        self,
        user_id: int,
        *,
        text_length: int,
        duration_sec: float | None,
        success: bool,
    ) -> None:
        async with self._lock:
            state = self._read_state()
            usage = self._ensure_usage_record(state, user_id, _today_key())
            usage["requests_count"] = int(usage["requests_count"]) + 1
            usage["total_characters"] = int(usage["total_characters"]) + max(0, int(text_length))
            usage["total_duration_sec"] = float(usage["total_duration_sec"]) + max(0.0, float(duration_sec or 0.0))
            if success:
                usage["successful_requests"] = int(usage["successful_requests"]) + 1
            else:
                usage["failed_requests"] = int(usage["failed_requests"]) + 1
            state["updated_at"] = _utc_now_iso()
            self._prune_usage(state)
            self._write_state(state)

    async def get_daily_usage(self, user_id: int, target_date: date) -> dict[str, Any]:
        state = self._read_state()
        usage = state.get("usage", {}).get(target_date.isoformat(), {}).get(str(user_id))
        if not usage:
            return _empty_usage()
        normalized = _empty_usage()
        for key in normalized.keys():
            normalized[key] = usage.get(key, normalized[key])
        return normalized

    async def get_user_stats(self, user_id: int, days: int = 7) -> dict[str, Any]:
        keys = self._period_keys(days)
        state = self._read_state()
        total = _empty_usage()
        for key in keys:
            payload = state.get("usage", {}).get(key, {}).get(str(user_id))
            if payload:
                self._merge_usage(total, payload)

        requests_count = int(total["requests_count"])
        success = int(total["successful_requests"])
        success_rate = (success / requests_count * 100.0) if requests_count else 0.0
        avg_duration = (float(total["total_duration_sec"]) / requests_count) if requests_count else 0.0

        return {
            "period_days": max(1, int(days)),
            "user_id": user_id,
            **total,
            "success_rate": round(success_rate, 2),
            "avg_duration_sec": round(avg_duration, 4),
        }

    async def get_global_stats(self, days: int = 7) -> dict[str, Any]:
        keys = self._period_keys(days)
        state = self._read_state()
        total = _empty_usage()
        unique_users: set[int] = set()

        for key in keys:
            users_for_day = state.get("usage", {}).get(key, {})
            for user_id_raw, payload in users_for_day.items():
                try:
                    unique_users.add(int(user_id_raw))
                except Exception:
                    continue
                self._merge_usage(total, payload)

        requests_count = int(total["requests_count"])
        success = int(total["successful_requests"])
        success_rate = (success / requests_count * 100.0) if requests_count else 0.0
        avg_requests = (requests_count / len(unique_users)) if unique_users else 0.0

        return {
            "period_days": max(1, int(days)),
            "unique_users": len(unique_users),
            **total,
            "success_rate": round(success_rate, 2),
            "avg_requests_per_user": round(avg_requests, 3),
        }

    def _period_keys(self, days: int) -> list[str]:
        span = max(1, int(days))
        today = datetime.now(timezone.utc).date()
        return [(today - timedelta(days=offset)).isoformat() for offset in range(span)]

    @staticmethod
    def _merge_usage(target: dict[str, Any], source: dict[str, Any]) -> None:
        target["requests_count"] = int(target["requests_count"]) + int(source.get("requests_count", 0))
        target["total_characters"] = int(target["total_characters"]) + int(source.get("total_characters", 0))
        target["total_duration_sec"] = float(target["total_duration_sec"]) + float(source.get("total_duration_sec", 0.0))
        target["successful_requests"] = int(target["successful_requests"]) + int(source.get("successful_requests", 0))
        target["failed_requests"] = int(target["failed_requests"]) + int(source.get("failed_requests", 0))

    def _ensure_usage_record(self, state: dict[str, Any], user_id: int, day_key: str) -> dict[str, Any]:
        usage = state.setdefault("usage", {})
        day = usage.setdefault(day_key, {})
        record = day.setdefault(str(user_id), _empty_usage())
        for key, default in _empty_usage().items():
            record.setdefault(key, default)
        return record

    def _prune_usage(self, state: dict[str, Any]) -> None:
        usage = state.get("usage", {})
        if not usage:
            return
        threshold = datetime.now(timezone.utc).date() - timedelta(days=self.retention_days)
        stale = []
        for key in usage.keys():
            try:
                key_date = date.fromisoformat(key)
            except Exception:
                stale.append(key)
                continue
            if key_date < threshold:
                stale.append(key)
        for key in stale:
            usage.pop(key, None)

    @staticmethod
    def _sanitize_limits_patch(patch: dict[str, Any]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        if "max_text_length" in patch:
            output["max_text_length"] = max(10, min(5000, int(patch["max_text_length"])))
        if "daily_limit" in patch:
            output["daily_limit"] = max(1, min(10000, int(patch["daily_limit"])))
        if "priority_level" in patch:
            output["priority_level"] = max(1, min(10, int(patch["priority_level"])))
        if "tts_enabled" in patch:
            output["tts_enabled"] = bool(patch["tts_enabled"])
        return output

    def _read_state(self) -> dict[str, Any]:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _write_state(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2)
        tmp_fd, tmp_name = tempfile.mkstemp(
            prefix=f"{self.state_path.name}.",
            suffix=".tmp",
            dir=str(self.state_path.parent),
            text=True,
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
                handle.write(body)
            os.replace(tmp_name, self.state_path)
        finally:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)


class TTSLimitsStore:
    def __init__(
        self,
        state_path: Path,
        *,
        default_max_text_length: int,
        default_daily_limit: int,
        default_priority_level: int,
        default_tts_enabled: bool,
        retention_days: int,
        database_url: str = "",
        database_echo: bool = False,
    ) -> None:
        if (database_url or "").strip():
            self._backend = PostgresTTSLimitsStore(
                database_url=database_url,
                default_max_text_length=default_max_text_length,
                default_daily_limit=default_daily_limit,
                default_priority_level=default_priority_level,
                default_tts_enabled=default_tts_enabled,
                retention_days=retention_days,
                echo=database_echo,
            )
        else:
            self._backend = FileTTSLimitsStore(
                state_path,
                default_max_text_length=default_max_text_length,
                default_daily_limit=default_daily_limit,
                default_priority_level=default_priority_level,
                default_tts_enabled=default_tts_enabled,
                retention_days=retention_days,
            )

    @property
    def backend_name(self) -> str:
        return self._backend.__class__.__name__

    async def startup(self) -> None:
        startup = getattr(self._backend, "startup", None)
        if callable(startup):
            await startup()

    async def close(self) -> None:
        close_fn = getattr(self._backend, "close", None)
        if callable(close_fn):
            await close_fn()

    def __getattr__(self, item):
        return getattr(self._backend, item)
