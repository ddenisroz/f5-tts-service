from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from ..audio_processing import sanitize_voice_name
from ..auth import verify_api_key
from ..schemas import CompatSynthesizeChannelRequest, UserTtsLimitsPatch
from ..voice_uploads import prepare_uploaded_voice_file, transcribe_voice_file

router = APIRouter(prefix="/api/tts", tags=["tts-compat"], dependencies=[Depends(verify_api_key)])


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    return bool(value)


@router.post("/synthesize-channel")
async def synthesize_channel(request: Request, payload: CompatSynthesizeChannelRequest) -> dict[str, Any]:
    blocked = {name.strip().lower() for name in payload.blocked_users if name and isinstance(name, str)}
    if payload.author.strip().lower() in blocked:
        return {"success": False, "error": "Author is blocked"}

    text = payload.text
    for word in payload.word_filter:
        if word:
            text = text.replace(word, "")
    text = text.strip()
    max_len = max(1, int(request.app.state.settings.max_input_text_length))
    if len(text) > max_len:
        return {
            "success": False,
            "audio_url": None,
            "voice": payload.voice or "female_1",
            "selected_voice": payload.voice or "female_1",
            "tts_type": "ai_f5",
            "duration": None,
            "error": f"Text too long. Maximum {max_len} characters",
        }
    if not text:
        return {
            "success": False,
            "audio_url": None,
            "voice": payload.voice or "female_1",
            "selected_voice": payload.voice or "female_1",
            "tts_type": "ai_f5",
            "duration": None,
            "error": "Text is empty after filtering",
        }

    preferred_voice = payload.voice or payload.tts_settings.get("voice")
    selected_voice = await request.app.state.voice_store.resolve_voice_for_user(payload.user_id, preferred_voice)
    tts_settings = payload.tts_settings if isinstance(payload.tts_settings, dict) else {}
    voice_settings = tts_settings.get("voice_settings", {}) if isinstance(tts_settings.get("voice_settings"), dict) else {}
    cfg_strength = voice_settings.get("cfg_strength", tts_settings.get("cfg_strength"))
    speed_preset = voice_settings.get("speed_preset", tts_settings.get("speed_preset"))
    remove_silence = _as_bool(voice_settings.get("remove_silence", tts_settings.get("remove_silence", False)))

    user_id = payload.user_id
    limits_service_enabled = bool(getattr(request.app.state.settings, "limits_enabled", False))
    if limits_service_enabled and isinstance(user_id, int):
        allowed, error, _, _ = await request.app.state.limits_store.validate_request(user_id, text)
        if not allowed:
            return {
                "success": False,
                "audio_url": None,
                "voice": selected_voice,
                "selected_voice": selected_voice,
                "tts_type": "ai_f5",
                "duration": None,
                "error": error,
            }

    provider_request = {
        "text": text,
        "voice": selected_voice,
        "tenant_id": f"channel:{payload.channel_name}",
        "channel_name": payload.channel_name,
        "author": payload.author,
        "user_id": user_id,
        "volume_level": payload.volume_level,
        "cfg_strength": cfg_strength,
        "speed_preset": speed_preset,
        "remove_silence": remove_silence,
        "metadata": {
            "compat": True,
            "cfg_strength": cfg_strength,
            "speed_preset": speed_preset,
            "remove_silence": remove_silence,
        },
    }
    result = await request.app.state.provider_synthesize(provider_request)
    success = bool(result.get("success"))
    duration = result.get("duration")

    if limits_service_enabled and isinstance(user_id, int):
        await request.app.state.limits_store.log_request(
            user_id,
            text_length=len(text),
            duration_sec=float(duration or 0.0),
            success=success,
        )

    return {
        "success": success,
        "audio_url": result.get("audio_url"),
        "voice": result.get("voice") or selected_voice,
        "selected_voice": result.get("selected_voice") or result.get("voice") or selected_voice,
        "tts_type": "ai_f5",
        "duration": duration,
        "error": result.get("error"),
    }


@router.get("/audio/{filename}")
async def get_audio(request: Request, filename: str) -> FileResponse:
    try:
        path = request.app.state.audio_store.resolve_path(filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return FileResponse(
        path,
        media_type=media_type,
        filename=path.name,
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/voices/global")
async def voices_global(request: Request) -> list[dict[str, Any]]:
    voices = await request.app.state.voice_store.list_global_voices()
    return [dict(voice, type="global", is_global=True) for voice in voices]


@router.get("/voices")
async def voices_all(request: Request, user_id: int | None = Query(default=None)) -> list[dict[str, Any]]:
    voices = await request.app.state.voice_store.list_available_voices(user_id=user_id)
    return [
        dict(
            voice,
            type="global" if voice.get("voice_type") == "global" else "user",
            is_global=voice.get("voice_type") == "global",
        )
        for voice in voices
    ]


@router.get("/voices/{voice_id}")
async def get_voice_info(request: Request, voice_id: int) -> dict[str, Any]:
    voice = await request.app.state.voice_store.get_voice_by_id(voice_id)
    if not voice:
        raise HTTPException(status_code=404, detail="Voice not found")
    payload = dict(voice)
    payload["type"] = "global" if payload.get("voice_type") == "global" else "user"
    payload["is_global"] = payload.get("voice_type") == "global"
    return payload


@router.get("/user/voices/{user_id}")
async def user_voices(request: Request, user_id: int) -> list[dict[str, Any]]:
    voices = await request.app.state.voice_store.list_user_voices(user_id)
    return [dict(voice, type="user", is_global=False) for voice in voices]


@router.post("/user/voices/upload")
async def upload_user_voice(
    request: Request,
    file: UploadFile = File(...),
    voice_name: str = Form(...),
    user_id: int = Form(...),
) -> dict[str, Any]:
    try:
        clean_name = sanitize_voice_name(voice_name)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    all_voices = await request.app.state.voice_store.list_all_voices()
    if any(
        int(item.get("owner_id") or 0) == user_id
        and str(item.get("name", "")).strip().lower() == clean_name.lower()
        for item in all_voices
    ):
        raise HTTPException(status_code=400, detail=f"Voice with name '{clean_name}' already exists")

    target_path, reference_text = await prepare_uploaded_voice_file(
        request.app,
        upload=file,
        filename_prefix=f"user_{user_id}_{clean_name}",
    )
    try:
        voice = await request.app.state.voice_store.create_voice(
            name=clean_name,
            owner_id=user_id,
            voice_type="user",
            file_path=str(target_path),
            is_public=False,
            reference_text=reference_text or None,
            cfg_strength=float(request.app.state.settings.f5_default_cfg_strength),
            speed_preset=str(request.app.state.settings.f5_default_speed_preset),
        )
    except ValueError as error:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(error))
    except Exception:
        target_path.unlink(missing_ok=True)
        raise
    return {"success": True, "status": "success", "voice": voice}


@router.delete("/user/voices/{voice_id}")
async def delete_user_voice(request: Request, voice_id: int, user_id: int = Query(...)) -> dict[str, Any]:
    voice = await request.app.state.voice_store.get_voice_by_id(voice_id)
    if not voice or int(voice.get("owner_id") or 0) != user_id:
        raise HTTPException(status_code=404, detail="Voice not found")
    file_path_raw = str(voice.get("file_path") or "").strip()
    await request.app.state.voice_store.delete_voice(voice_id)
    if file_path_raw:
        resolved = Path(file_path_raw).resolve()
        base = request.app.state.voice_files_dir.resolve()
        try:
            resolved.relative_to(base)
            resolved.unlink(missing_ok=True)
        except ValueError:
            pass
    return {"success": True}


@router.put("/user/voices/{voice_id}/settings")
async def update_user_voice_settings(request: Request, voice_id: int, settings: dict[str, Any]) -> dict[str, Any]:
    updated = await request.app.state.voice_store.update_voice_settings(voice_id, settings)
    if not updated:
        raise HTTPException(status_code=404, detail="Voice not found")
    return {"success": True, "voice": updated}


@router.get("/user/voices/enabled/{user_id}")
async def get_enabled_voices(request: Request, user_id: int) -> dict[str, Any]:
    voice_ids = await request.app.state.voice_store.get_enabled_voice_ids(user_id)
    return {"success": True, "voice_ids": voice_ids, "enabled_voice_ids": voice_ids}


@router.post("/user/voices/enabled/{user_id}")
async def set_enabled_voices(request: Request, user_id: int, voice_ids: list[int]) -> dict[str, Any]:
    stored = await request.app.state.voice_store.set_enabled_voice_ids(user_id, voice_ids)
    return {"success": True, "voice_ids": stored, "enabled_voice_ids": stored}


@router.put("/user/voices/enabled/{user_id}/{voice_id}")
async def toggle_enabled_voice(
    request: Request,
    user_id: int,
    voice_id: int,
    is_enabled: bool = Query(...),
) -> dict[str, Any]:
    stored = await request.app.state.voice_store.toggle_enabled_voice_id(user_id, voice_id, is_enabled)
    return {"success": True, "voice_ids": stored, "enabled_voice_ids": stored}


@router.put("/user/voices/{voice_id}/rename")
async def rename_user_voice(
    request: Request,
    voice_id: int,
    user_id: int = Query(...),
    new_name: str = Form(...),
) -> dict[str, Any]:
    voice = await request.app.state.voice_store.get_voice_by_id(voice_id)
    if not voice or int(voice.get("owner_id") or 0) != user_id:
        raise HTTPException(status_code=404, detail="Voice not found")
    try:
        clean_name = sanitize_voice_name(new_name)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    all_voices = await request.app.state.voice_store.list_all_voices()
    if any(
        int(item.get("id") or 0) != voice_id
        and int(item.get("owner_id") or 0) == user_id
        and str(item.get("name", "")).strip().lower() == clean_name.lower()
        for item in all_voices
    ):
        raise HTTPException(status_code=400, detail=f"Voice with name '{clean_name}' already exists")
    try:
        updated = await request.app.state.voice_store.rename_voice(voice_id, clean_name)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"success": True, "voice": updated}


@router.post("/user/voices/{voice_id}/retranscribe")
async def retranscribe_user_voice(request: Request, voice_id: int, user_id: int = Query(...)) -> dict[str, Any]:
    if not request.app.state.transcriber.enabled:
        raise HTTPException(status_code=503, detail="Transcriber is disabled")
    voice = await request.app.state.voice_store.get_voice_by_id(voice_id)
    if not voice or int(voice.get("owner_id") or 0) != user_id:
        raise HTTPException(status_code=404, detail="Voice not found")
    file_path_raw = str(voice.get("file_path") or "").strip()
    if not file_path_raw:
        raise HTTPException(status_code=400, detail="Voice has no file_path")
    file_path = Path(file_path_raw).resolve()
    base = request.app.state.voice_files_dir.resolve()
    try:
        file_path.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid voice file path")
    try:
        reference_text = await transcribe_voice_file(request.app, file_path)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))
    updated = await request.app.state.voice_store.update_voice_settings(
        voice_id,
        {"reference_text": reference_text},
    )
    return {"success": True, "status": "success", "voice": updated, "reference_text": reference_text}


@router.post("/user/voices/{voice_id}/transcribe")
async def transcribe_user_voice(request: Request, voice_id: int, user_id: int = Query(...)) -> dict[str, Any]:
    return await retranscribe_user_voice(request, voice_id, user_id)


@router.get("/user/tts-limits/{user_id}")
async def get_user_tts_limits(request: Request, user_id: int) -> dict[str, Any]:
    limits = await request.app.state.limits_store.get_user_limits(user_id)
    return {"success": True, "user_id": user_id, **limits}


@router.put("/user/tts-limits/{user_id}")
async def update_user_tts_limits(
    request: Request,
    user_id: int,
    payload: UserTtsLimitsPatch,
) -> dict[str, Any]:
    patch = payload.model_dump(exclude_none=True)
    limits = await request.app.state.limits_store.update_user_limits(user_id, patch)
    return {"success": True, "user_id": user_id, **limits}


@router.get("/user/tts-stats/{user_id}")
async def get_user_tts_stats(request: Request, user_id: int, days: int = Query(default=7, ge=1, le=90)) -> dict[str, Any]:
    stats = await request.app.state.limits_store.get_user_stats(user_id, days=days)
    return {"success": True, **stats}


@router.get("/stats/global")
@router.get("/tts/stats/global")
async def get_global_tts_stats(request: Request, days: int = Query(default=7, ge=1, le=90)) -> dict[str, Any]:
    stats = await request.app.state.limits_store.get_global_stats(days=days)
    return {"success": True, **stats}


@router.post("/enable")
async def enable_tts(request: Request, user_id: int = Query(..., ge=1)) -> dict[str, Any]:
    limits = await request.app.state.limits_store.update_user_limits(user_id, {"tts_enabled": True})
    return {"success": True, "message": "TTS enabled", "status": {"enabled": limits["tts_enabled"]}}


@router.post("/disable")
async def disable_tts(request: Request, user_id: int = Query(..., ge=1)) -> dict[str, Any]:
    limits = await request.app.state.limits_store.update_user_limits(user_id, {"tts_enabled": False})
    return {"success": True, "message": "TTS disabled", "status": {"enabled": limits["tts_enabled"]}}


@router.get("/status")
async def get_tts_status(request: Request, user_id: int = Query(..., ge=1)) -> dict[str, Any]:
    limits = await request.app.state.limits_store.get_user_limits(user_id)
    return {"success": True, "enabled": bool(limits["tts_enabled"]), "status": {"enabled": bool(limits["tts_enabled"])}}
