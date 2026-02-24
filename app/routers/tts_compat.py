from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from ..auth import verify_api_key
from ..schemas import CompatSynthesizeChannelRequest

router = APIRouter(prefix="/api/tts", tags=["tts-compat"], dependencies=[Depends(verify_api_key)])


@router.post("/synthesize-channel")
async def synthesize_channel(request: Request, payload: CompatSynthesizeChannelRequest) -> dict[str, Any]:
    blocked = {name.strip().lower() for name in payload.blocked_users if name and isinstance(name, str)}
    if payload.author.strip().lower() in blocked:
        return {"success": False, "error": "Author is blocked"}

    text = payload.text
    for word in payload.word_filter:
        if word:
            text = text.replace(word, "")

    selected_voice = (
        payload.voice
        or payload.tts_settings.get("voice")
        or "female_1"
    )
    provider_request = {
        "text": text,
        "voice": selected_voice,
        "tenant_id": f"channel:{payload.channel_name}",
        "channel_name": payload.channel_name,
        "author": payload.author,
        "user_id": payload.user_id,
        "volume_level": payload.volume_level,
        "metadata": {"compat": True},
    }
    result = await request.app.state.provider_synthesize(provider_request)
    return {
        "success": bool(result.get("success")),
        "audio_url": result.get("audio_url"),
        "voice": selected_voice,
        "selected_voice": selected_voice,
        "tts_type": "ai_f5",
        "duration": result.get("duration"),
        "error": result.get("error"),
    }


@router.get("/audio/{filename}")
async def get_audio(request: Request, filename: str) -> FileResponse:
    path = request.app.state.audio_store.resolve_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path)


@router.get("/voices/global")
async def voices_global(request: Request) -> list[dict[str, Any]]:
    voices = await request.app.state.voice_store.list_global_voices()
    return [dict(voice, type="global", is_global=True) for voice in voices]


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
    file_bytes = await file.read()
    filename = f"user_{user_id}_{file.filename}"
    target = request.app.state.voice_files_dir / filename
    target.write_bytes(file_bytes)
    voice = await request.app.state.voice_store.create_voice(
        name=voice_name.strip(),
        owner_id=user_id,
        voice_type="user",
        file_path=str(target),
        is_public=False,
    )
    return {"success": True, "voice": voice}


@router.delete("/user/voices/{voice_id}")
async def delete_user_voice(request: Request, voice_id: int, user_id: int = Query(...)) -> dict[str, Any]:
    voice = await request.app.state.voice_store.get_voice_by_id(voice_id)
    if not voice or int(voice.get("owner_id") or 0) != user_id:
        raise HTTPException(status_code=404, detail="Voice not found")
    await request.app.state.voice_store.delete_voice(voice_id)
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
    return {"success": True, "voice_ids": voice_ids}


@router.post("/user/voices/enabled/{user_id}")
async def set_enabled_voices(request: Request, user_id: int, voice_ids: list[int]) -> dict[str, Any]:
    stored = await request.app.state.voice_store.set_enabled_voice_ids(user_id, voice_ids)
    return {"success": True, "voice_ids": stored}


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
    updated = await request.app.state.voice_store.rename_voice(voice_id, new_name.strip())
    return {"success": True, "voice": updated}


@router.post("/user/voices/{voice_id}/retranscribe")
async def retranscribe_user_voice(request: Request, voice_id: int, user_id: int = Query(...)) -> dict[str, Any]:
    voice = await request.app.state.voice_store.get_voice_by_id(voice_id)
    if not voice or int(voice.get("owner_id") or 0) != user_id:
        raise HTTPException(status_code=404, detail="Voice not found")
    updated = await request.app.state.voice_store.update_voice_settings(
        voice_id,
        {"reference_text": (voice.get("reference_text") or "")},
    )
    return {"success": True, "voice": updated}

