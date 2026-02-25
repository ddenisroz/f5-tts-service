from __future__ import annotations

from pathlib import Path
from typing import Any


async def resolve_synthesis_context(app, payload: dict[str, Any]) -> dict[str, Any]:
    settings = app.state.settings
    voice_store = app.state.voice_store

    user_id_raw = payload.get("user_id")
    user_id: int | None = None
    if user_id_raw is not None and str(user_id_raw).strip():
        try:
            user_id = int(user_id_raw)
        except Exception:
            user_id = None
    requested_voice = str(payload.get("voice") or "").strip()

    voice_record = await voice_store.resolve_voice_record_for_user(user_id, requested_voice)
    selected_voice = str((voice_record or {}).get("name") or "female_1")

    cfg_strength = payload.get("cfg_strength")
    if cfg_strength is None and voice_record is not None:
        cfg_strength = voice_record.get("cfg_strength")
    if cfg_strength is None:
        cfg_strength = settings.f5_default_cfg_strength

    speed_preset = payload.get("speed_preset")
    if speed_preset is None and voice_record is not None:
        speed_preset = voice_record.get("speed_preset")
    if not speed_preset:
        speed_preset = settings.f5_default_speed_preset

    reference_text = ""
    if voice_record is not None:
        reference_text = (voice_record.get("reference_text") or "").strip()
    if not reference_text:
        reference_text = settings.f5_default_ref_text.strip()

    ref_audio_path = ""
    if voice_record is not None and voice_record.get("file_path"):
        base = app.state.voice_files_dir.resolve()
        raw_value = str(voice_record["file_path"]).strip()
        raw_path = Path(raw_value)
        candidates: list[Path] = []
        if raw_path.is_absolute():
            candidates.append(raw_path)
        else:
            candidates.append((settings.base_path / raw_path).resolve())
            candidates.append((base / raw_path.name).resolve())
        for candidate in candidates:
            try:
                candidate.relative_to(base)
                ref_audio_path = str(candidate)
                break
            except ValueError:
                continue
        if not ref_audio_path:
            raise ValueError(f"Invalid reference path for voice '{selected_voice}'")
    if not ref_audio_path:
        ref_audio_path = str(settings.default_ref_audio_path)

    ref_audio = Path(ref_audio_path).resolve()
    if not ref_audio.exists():
        raise ValueError(
            f"Reference audio is missing for voice '{selected_voice}'. "
            f"Expected file: {ref_audio}"
        )

    return {
        "selected_voice": selected_voice,
        "reference_audio_path": str(ref_audio),
        "reference_text": reference_text,
        "cfg_strength": float(cfg_strength),
        "speed_preset": str(speed_preset),
    }
