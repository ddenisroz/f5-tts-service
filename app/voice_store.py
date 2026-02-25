from __future__ import annotations

import json
import os
import random
import tempfile
from asyncio import Lock
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schemas import VoiceRecord, VoiceStats
from .voice_store_postgres import PostgresVoiceStore


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FileVoiceStore:
    def __init__(self, state_path: Path, voices_dir: Path) -> None:
        self.state_path = state_path
        self.voices_dir = voices_dir
        self._lock = Lock()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            self._write_state(
                {
                    "next_id": 2,
                    "updated_at": _utc_now_iso(),
                    "voices": [
                        {
                            "id": 1,
                            "name": "female_1",
                            "file_path": "",
                            "voice_type": "global",
                            "owner_id": None,
                            "is_public": True,
                            "is_active": True,
                            "reference_text": None,
                            "created_at": _utc_now_iso(),
                            "cfg_strength": None,
                            "speed_preset": None,
                        }
                    ],
                    "enabled": {},
                }
            )

    async def startup(self) -> None:
        return

    async def close(self) -> None:
        return

    async def list_global_voices(self) -> list[dict[str, Any]]:
        state = self._read_state()
        return [v for v in state["voices"] if v.get("voice_type") == "global" and v.get("is_active", True)]

    async def list_available_voices(self, user_id: int | None) -> list[dict[str, Any]]:
        return self._active_voices_for_user(user_id)

    async def list_user_voices(self, user_id: int) -> list[dict[str, Any]]:
        state = self._read_state()
        return [
            v
            for v in state["voices"]
            if int(v.get("owner_id") or 0) == user_id and v.get("is_active", True)
        ]

    async def list_all_voices(self) -> list[dict[str, Any]]:
        return self._read_state()["voices"]

    async def get_voice_by_id(self, voice_id: int) -> dict[str, Any] | None:
        for voice in self._read_state()["voices"]:
            if int(voice["id"]) == voice_id:
                return voice
        return None

    async def get_voice_by_name(self, name: str) -> dict[str, Any] | None:
        normalized = name.strip().lower()
        for voice in self._read_state()["voices"]:
            if str(voice.get("name", "")).strip().lower() == normalized:
                return voice
        return None

    async def create_voice(
        self,
        *,
        name: str,
        owner_id: int | None,
        voice_type: str,
        file_path: str,
        is_public: bool,
        reference_text: str | None = None,
        cfg_strength: float | None = None,
        speed_preset: str | None = None,
    ) -> dict[str, Any]:
        async with self._lock:
            state = self._read_state()
            for existing in state["voices"]:
                if self._is_name_conflict(
                    existing=existing,
                    candidate_name=name,
                    candidate_type=voice_type,
                    candidate_owner_id=owner_id,
                ):
                    raise ValueError(f"Voice '{name}' already exists")

            voice_id = int(state["next_id"])
            voice = VoiceRecord(
                id=voice_id,
                name=name,
                file_path=file_path,
                voice_type=voice_type,
                owner_id=owner_id,
                is_public=is_public,
                is_active=True,
                reference_text=reference_text,
                created_at=_utc_now_iso(),
                cfg_strength=cfg_strength,
                speed_preset=speed_preset,
                enabled_user_ids=[],
            ).model_dump()
            state["voices"].append(voice)
            state["next_id"] = voice_id + 1
            state["updated_at"] = _utc_now_iso()
            self._write_state(state)
            return voice

    async def update_voice_settings(self, voice_id: int, patch: dict[str, Any]) -> dict[str, Any] | None:
        async with self._lock:
            state = self._read_state()
            for voice in state["voices"]:
                if int(voice["id"]) == voice_id:
                    for key in ("reference_text", "cfg_strength", "speed_preset"):
                        if key in patch:
                            voice[key] = patch[key]
                    state["updated_at"] = _utc_now_iso()
                    self._write_state(state)
                    return voice
        return None

    async def rename_voice(self, voice_id: int, new_name: str) -> dict[str, Any] | None:
        async with self._lock:
            state = self._read_state()
            target: dict[str, Any] | None = None
            for voice in state["voices"]:
                if int(voice["id"]) == voice_id:
                    target = voice
                    break
            if target is None:
                return None
            for existing in state["voices"]:
                if self._is_name_conflict(
                    existing=existing,
                    candidate_name=new_name,
                    candidate_type=str(target.get("voice_type") or "user"),
                    candidate_owner_id=target.get("owner_id"),
                    exclude_id=voice_id,
                ):
                    raise ValueError(f"Voice '{new_name}' already exists")
            target["name"] = new_name
            state["updated_at"] = _utc_now_iso()
            self._write_state(state)
            return target

    async def toggle_voice(self, voice_id: int) -> dict[str, Any] | None:
        async with self._lock:
            state = self._read_state()
            for voice in state["voices"]:
                if int(voice["id"]) == voice_id:
                    voice["is_active"] = not bool(voice.get("is_active", True))
                    state["updated_at"] = _utc_now_iso()
                    self._write_state(state)
                    return voice
        return None

    async def delete_voice(self, voice_id: int) -> bool:
        async with self._lock:
            state = self._read_state()
            before = len(state["voices"])
            state["voices"] = [voice for voice in state["voices"] if int(voice["id"]) != voice_id]
            if len(state["voices"]) == before:
                return False
            state["updated_at"] = _utc_now_iso()
            self._write_state(state)
            return True

    async def get_enabled_voice_ids(self, user_id: int) -> list[int]:
        state = self._read_state()
        enabled_map = state.get("enabled", {})
        values = enabled_map.get(str(user_id), [])
        return [int(v) for v in values]

    async def set_enabled_voice_ids(self, user_id: int, voice_ids: list[int]) -> list[int]:
        async with self._lock:
            state = self._read_state()
            valid_ids = {int(v["id"]) for v in state["voices"]}
            filtered = sorted({int(v) for v in voice_ids if int(v) in valid_ids})
            state.setdefault("enabled", {})[str(user_id)] = filtered
            state["updated_at"] = _utc_now_iso()
            self._write_state(state)
            return filtered

    async def toggle_enabled_voice_id(self, user_id: int, voice_id: int, is_enabled: bool) -> list[int]:
        current = set(await self.get_enabled_voice_ids(user_id))
        valid_ids = {int(voice["id"]) for voice in self._read_state()["voices"]}
        if voice_id not in valid_ids:
            return sorted(current)
        if is_enabled:
            current.add(voice_id)
        else:
            current.discard(voice_id)
        return await self.set_enabled_voice_ids(user_id, sorted(current))

    async def resolve_voice_for_user(self, user_id: int | None, requested_voice: str | None) -> str:
        selected = await self.resolve_voice_record_for_user(user_id, requested_voice)
        if not selected:
            return "female_1"
        return str(selected["name"])

    async def resolve_voice_record_for_user(
        self,
        user_id: int | None,
        requested_voice: str | None,
    ) -> dict[str, Any] | None:
        active = self._active_voices_for_user(user_id)
        if not active:
            return None

        enabled_pool = self._filter_by_enabled(user_id, active)
        effective_pool = enabled_pool if enabled_pool else active
        requested = (requested_voice or "").strip()
        if requested and requested.lower() != "random":
            matched = self._find_by_name(effective_pool, requested)
            if matched:
                return matched
        return random.choice(effective_pool)

    async def stats(self) -> VoiceStats:
        state = self._read_state()
        voices = state["voices"]
        total = len(voices)
        global_count = len([v for v in voices if v.get("voice_type") == "global"])
        user_count = len([v for v in voices if v.get("voice_type") != "global"])
        active_count = len([v for v in voices if v.get("is_active", True)])
        return VoiceStats(
            total_voices=total,
            global_voices=global_count,
            user_voices=user_count,
            active_voices=active_count,
            updated_at=datetime.now(timezone.utc),
        )

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

    def _active_voices_for_user(self, user_id: int | None) -> list[dict[str, Any]]:
        voices = self._read_state()["voices"]
        active = [voice for voice in voices if voice.get("is_active", True)]
        if user_id is None:
            return [voice for voice in active if voice.get("voice_type") == "global"]
        user_specific = []
        for voice in active:
            if voice.get("voice_type") == "global":
                user_specific.append(voice)
            elif int(voice.get("owner_id") or 0) == int(user_id):
                user_specific.append(voice)
        return user_specific

    def _filter_by_enabled(self, user_id: int | None, voices: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if user_id is None:
            return voices
        enabled_ids = set(int(item) for item in self._read_state().get("enabled", {}).get(str(user_id), []))
        if not enabled_ids:
            return voices
        return [voice for voice in voices if int(voice["id"]) in enabled_ids]

    @staticmethod
    def _find_by_name(voices: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
        lowered = name.strip().lower()
        for voice in voices:
            if str(voice.get("name", "")).strip().lower() == lowered:
                return voice
        return None

    @staticmethod
    def _is_name_conflict(
        *,
        existing: dict[str, Any],
        candidate_name: str,
        candidate_type: str,
        candidate_owner_id: int | None,
        exclude_id: int | None = None,
    ) -> bool:
        if exclude_id is not None and int(existing.get("id") or 0) == int(exclude_id):
            return False
        if str(existing.get("name", "")).strip().lower() != candidate_name.strip().lower():
            return False

        existing_type = str(existing.get("voice_type") or "user").strip().lower()
        existing_owner = existing.get("owner_id")
        normalized_type = str(candidate_type or "user").strip().lower()
        owner = int(candidate_owner_id) if candidate_owner_id is not None else None

        # Global voice names must be unique across all voices.
        if normalized_type == "global":
            return True
        # User voice name cannot collide with any global voice.
        if existing_type == "global":
            return True
        # User voice names must be unique per owner.
        return int(existing_owner or 0) == int(owner or 0)


class VoiceStore:
    def __init__(
        self,
        state_path: Path,
        voices_dir: Path,
        *,
        database_url: str = "",
        database_echo: bool = False,
    ) -> None:
        if (database_url or "").strip():
            self._backend = PostgresVoiceStore(database_url=database_url, voices_dir=voices_dir, echo=database_echo)
        else:
            self._backend = FileVoiceStore(state_path=state_path, voices_dir=voices_dir)

    @property
    def backend(self):
        return self._backend

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
