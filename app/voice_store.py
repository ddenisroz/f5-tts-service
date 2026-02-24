from __future__ import annotations

import json
from asyncio import Lock
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schemas import VoiceRecord, VoiceStats


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class VoiceStore:
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

    async def list_global_voices(self) -> list[dict[str, Any]]:
        state = self._read_state()
        return [v for v in state["voices"] if v.get("voice_type") == "global"]

    async def list_user_voices(self, user_id: int) -> list[dict[str, Any]]:
        state = self._read_state()
        return [v for v in state["voices"] if int(v.get("owner_id") or 0) == user_id]

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
    ) -> dict[str, Any]:
        async with self._lock:
            state = self._read_state()
            voice_id = int(state["next_id"])
            voice = VoiceRecord(
                id=voice_id,
                name=name,
                file_path=file_path,
                voice_type=voice_type,
                owner_id=owner_id,
                is_public=is_public,
                is_active=True,
                reference_text=None,
                created_at=_utc_now_iso(),
                cfg_strength=None,
                speed_preset=None,
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
            for voice in state["voices"]:
                if int(voice["id"]) == voice_id:
                    voice["name"] = new_name
                    state["updated_at"] = _utc_now_iso()
                    self._write_state(state)
                    return voice
        return None

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
        self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

