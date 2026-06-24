from __future__ import annotations

import asyncio
from pathlib import Path

from app.voice_store import FileVoiceStore


def _write_voice_file(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"stub")
    return path


def test_file_voice_store_filters_missing_reference_files_from_available_lists(workspace_tmp_path) -> None:
    voices_dir = workspace_tmp_path / "voices"
    state_path = workspace_tmp_path / "voices.json"
    store = FileVoiceStore(state_path, voices_dir)

    global_path = _write_voice_file(voices_dir / "global.wav")
    broken_path = voices_dir / "broken.wav"
    broken_path.write_bytes(b"stub")

    asyncio.run(
        store.create_voice(
            name="default_voice",
            owner_id=None,
            voice_type="global",
            file_path=str(global_path),
            is_public=True,
        )
    )
    asyncio.run(
        store.create_voice(
            name="broken_user",
            owner_id=7,
            voice_type="user",
            file_path=str(broken_path),
            is_public=False,
        )
    )
    broken_path.unlink()

    available = asyncio.run(store.list_available_voices(user_id=7))
    user_voices = asyncio.run(store.list_user_voices(user_id=7))
    all_voices = asyncio.run(store.list_all_voices())

    assert [voice["name"] for voice in available] == ["default_voice"]
    assert user_voices == []
    assert any(voice["name"] == "broken_user" and voice["is_usable"] is False for voice in all_voices)


def test_file_voice_store_drops_deleted_or_missing_voices_from_enabled_pool(workspace_tmp_path) -> None:
    voices_dir = workspace_tmp_path / "voices"
    state_path = workspace_tmp_path / "voices.json"
    store = FileVoiceStore(state_path, voices_dir)
    voice_path = _write_voice_file(voices_dir / "user.wav")

    voice = asyncio.run(
        store.create_voice(
            name="user_voice",
            owner_id=15,
            voice_type="user",
            file_path=str(voice_path),
            is_public=False,
        )
    )
    asyncio.run(store.set_enabled_voice_ids(15, [int(voice["id"])]))

    assert asyncio.run(store.get_enabled_voice_ids(15)) == [int(voice["id"])]

    voice_path.unlink()
    assert asyncio.run(store.get_enabled_voice_ids(15)) == []

    replacement_path = _write_voice_file(voices_dir / "user-2.wav")
    replacement = asyncio.run(
        store.create_voice(
            name="user_voice_2",
            owner_id=15,
            voice_type="user",
            file_path=str(replacement_path),
            is_public=False,
        )
    )
    asyncio.run(store.set_enabled_voice_ids(15, [int(replacement["id"])]))
    asyncio.run(store.delete_voice(int(replacement["id"])))

    assert asyncio.run(store.get_enabled_voice_ids(15)) == []


def test_file_voice_store_raises_explicit_error_for_unavailable_requested_voice(workspace_tmp_path) -> None:
    voices_dir = workspace_tmp_path / "voices"
    state_path = workspace_tmp_path / "voices.json"
    store = FileVoiceStore(state_path, voices_dir)
    global_path = _write_voice_file(voices_dir / "global.wav")

    asyncio.run(
        store.create_voice(
            name="default_voice",
            owner_id=None,
            voice_type="global",
            file_path=str(global_path),
            is_public=True,
        )
    )

    try:
        asyncio.run(store.resolve_voice_record_for_user(5, "ghost_voice"))
    except ValueError as error:
        assert "ghost_voice" in str(error)
    else:  # pragma: no cover - safety
        raise AssertionError("Expected explicit ValueError for unavailable voice")
