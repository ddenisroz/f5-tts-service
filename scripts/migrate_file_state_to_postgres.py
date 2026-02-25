from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, text

from app.config import get_settings
from app.limits_store_postgres import PostgresTTSLimitsStore, UsageDailyRow, UserLimitsRow
from app.voice_store_postgres import PostgresVoiceStore, UserVoiceEnabledRow, VoiceRow


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_datetime(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        value = str(raw).strip()
        if not value:
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


async def _migrate_voices(store: PostgresVoiceStore, payload: dict[str, Any], *, replace: bool) -> dict[str, int]:
    voices = payload.get("voices", [])
    enabled = payload.get("enabled", {})
    if not isinstance(voices, list):
        voices = []
    if not isinstance(enabled, dict):
        enabled = {}

    inserted_voices = 0
    inserted_enabled = 0

    async with store.session_factory() as session:
        async with session.begin():
            if replace and voices:
                await session.execute(delete(UserVoiceEnabledRow))
                await session.execute(delete(VoiceRow))

            for item in voices:
                if not isinstance(item, dict):
                    continue
                voice_id_raw = item.get("id")
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                try:
                    voice_id = int(voice_id_raw)
                except Exception:
                    continue

                row = VoiceRow(
                    id=voice_id,
                    name=name,
                    file_path=str(item.get("file_path") or ""),
                    voice_type=str(item.get("voice_type") or "user"),
                    owner_id=int(item["owner_id"]) if item.get("owner_id") is not None else None,
                    is_public=bool(item.get("is_public", False)),
                    is_active=bool(item.get("is_active", True)),
                    reference_text=(str(item.get("reference_text")) if item.get("reference_text") is not None else None),
                    created_at=_parse_datetime(item.get("created_at")),
                    cfg_strength=(float(item.get("cfg_strength")) if item.get("cfg_strength") is not None else None),
                    speed_preset=(str(item.get("speed_preset")) if item.get("speed_preset") is not None else None),
                )
                await session.merge(row)
                inserted_voices += 1

            if replace and enabled:
                await session.execute(delete(UserVoiceEnabledRow))

            for user_id_raw, ids in enabled.items():
                try:
                    user_id = int(user_id_raw)
                except Exception:
                    continue
                if not isinstance(ids, list):
                    continue
                for voice_id_raw in ids:
                    try:
                        voice_id = int(voice_id_raw)
                    except Exception:
                        continue
                    await session.merge(UserVoiceEnabledRow(user_id=user_id, voice_id=voice_id, is_enabled=True))
                    inserted_enabled += 1

            max_id = await session.scalar(select(func.max(VoiceRow.id)))
            if max_id is not None:
                await session.execute(
                    text("SELECT setval(pg_get_serial_sequence('voices', 'id'), :max_id, true)"),
                    {"max_id": int(max_id)},
                )

    return {"voices": inserted_voices, "enabled_links": inserted_enabled}


async def _migrate_limits(
    store: PostgresTTSLimitsStore,
    payload: dict[str, Any],
    *,
    replace: bool,
) -> dict[str, int]:
    users = payload.get("users", {})
    usage = payload.get("usage", {})
    if not isinstance(users, dict):
        users = {}
    if not isinstance(usage, dict):
        usage = {}

    inserted_users = 0
    inserted_usage_rows = 0

    async with store.session_factory() as session:
        async with session.begin():
            if replace and users:
                await session.execute(delete(UserLimitsRow))
            if replace and usage:
                await session.execute(delete(UsageDailyRow))

            for user_id_raw, patch in users.items():
                try:
                    user_id = int(user_id_raw)
                except Exception:
                    continue
                if not isinstance(patch, dict):
                    continue
                row = UserLimitsRow(
                    user_id=user_id,
                    max_text_length=(int(patch["max_text_length"]) if patch.get("max_text_length") is not None else None),
                    daily_limit=(int(patch["daily_limit"]) if patch.get("daily_limit") is not None else None),
                    priority_level=(int(patch["priority_level"]) if patch.get("priority_level") is not None else None),
                    tts_enabled=(bool(patch["tts_enabled"]) if patch.get("tts_enabled") is not None else None),
                    updated_at=datetime.now(timezone.utc),
                )
                await session.merge(row)
                inserted_users += 1

            for day_raw, user_payload in usage.items():
                try:
                    day = datetime.fromisoformat(str(day_raw)).date()
                except Exception:
                    continue
                if not isinstance(user_payload, dict):
                    continue
                for user_id_raw, stats in user_payload.items():
                    try:
                        user_id = int(user_id_raw)
                    except Exception:
                        continue
                    if not isinstance(stats, dict):
                        continue
                    row = UsageDailyRow(
                        day=day,
                        user_id=user_id,
                        requests_count=int(stats.get("requests_count", 0) or 0),
                        total_characters=int(stats.get("total_characters", 0) or 0),
                        total_duration_sec=float(stats.get("total_duration_sec", 0.0) or 0.0),
                        successful_requests=int(stats.get("successful_requests", 0) or 0),
                        failed_requests=int(stats.get("failed_requests", 0) or 0),
                        updated_at=datetime.now(timezone.utc),
                    )
                    await session.merge(row)
                    inserted_usage_rows += 1

    return {"user_limits": inserted_users, "usage_rows": inserted_usage_rows}


async def _run(replace: bool) -> None:
    settings = get_settings()
    database_url = (settings.database_url or "").strip()
    if not database_url:
        raise RuntimeError("F5_TTS_DATABASE_URL must be set before migration.")

    voice_file = settings.voices_state_path
    limits_file = settings.limits_state_path

    voice_payload = _read_json(voice_file)
    limits_payload = _read_json(limits_file)

    voice_store = PostgresVoiceStore(database_url=database_url, voices_dir=settings.voices_dir_path, echo=settings.database_echo)
    limits_store = PostgresTTSLimitsStore(
        database_url=database_url,
        default_max_text_length=settings.limit_default_max_text_length,
        default_daily_limit=settings.limit_default_daily_requests,
        default_priority_level=settings.limit_default_priority_level,
        default_tts_enabled=settings.limit_default_tts_enabled,
        retention_days=settings.limits_retention_days,
        echo=settings.database_echo,
    )
    await voice_store.startup()
    await limits_store.startup()
    try:
        if voice_payload:
            voice_stats = await _migrate_voices(voice_store, voice_payload, replace=replace)
            print(f"voices migrated: {voice_stats}")
        else:
            print(f"voices state file is empty or missing: {voice_file}")

        if limits_payload:
            limits_stats = await _migrate_limits(limits_store, limits_payload, replace=replace)
            print(f"limits migrated: {limits_stats}")
        else:
            print(f"limits state file is empty or missing: {limits_file}")
    finally:
        await limits_store.close()
        await voice_store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate file state (voices/limits) into PostgreSQL tables.")
    parser.add_argument(
        "--mode",
        choices=("replace", "merge"),
        default="replace",
        help="replace: clear target tables before insert; merge: upsert without clearing",
    )
    args = parser.parse_args()
    asyncio.run(_run(replace=args.mode == "replace"))


if __name__ == "__main__":
    main()
