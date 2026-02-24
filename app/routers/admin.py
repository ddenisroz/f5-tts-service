from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile

from ..auth import verify_api_key

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(verify_api_key)])


@router.get("/voices")
async def get_admin_voices(request: Request) -> dict[str, Any]:
    voices = await request.app.state.voice_store.list_all_voices()
    global_voices = [voice for voice in voices if voice.get("voice_type") == "global"]
    user_voices = [voice for voice in voices if voice.get("voice_type") != "global"]
    return {
        "success": True,
        "voices": voices,
        "global_voices": global_voices,
        "user_voices": user_voices,
    }


@router.post("/voices/upload")
async def upload_global_voice(
    request: Request,
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
) -> dict[str, Any]:
    file_bytes = await file.read()
    filename = f"global_{file.filename}"
    target = request.app.state.voice_files_dir / filename
    target.write_bytes(file_bytes)
    voice = await request.app.state.voice_store.create_voice(
        name=(name or file.filename).strip(),
        owner_id=None,
        voice_type="global",
        file_path=str(target),
        is_public=True,
    )
    return {"success": True, "voice": voice}


@router.delete("/voices/{voice_id}")
async def delete_voice(request: Request, voice_id: int) -> dict[str, Any]:
    deleted = await request.app.state.voice_store.delete_voice(voice_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Voice not found")
    return {"success": True}


@router.put("/voices/{voice_id}/rename")
async def rename_voice(request: Request, voice_id: int, new_name: str = Query(...)) -> dict[str, Any]:
    updated = await request.app.state.voice_store.rename_voice(voice_id, new_name.strip())
    if not updated:
        raise HTTPException(status_code=404, detail="Voice not found")
    return {"success": True, "voice": updated}


@router.put("/voices/{voice_id}/settings")
async def update_voice_settings(request: Request, voice_id: int, settings: dict[str, Any]) -> dict[str, Any]:
    updated = await request.app.state.voice_store.update_voice_settings(voice_id, settings)
    if not updated:
        raise HTTPException(status_code=404, detail="Voice not found")
    return {"success": True, "voice": updated}


@router.post("/voices/{voice_id}/toggle")
async def toggle_voice(request: Request, voice_id: int) -> dict[str, Any]:
    updated = await request.app.state.voice_store.toggle_voice(voice_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Voice not found")
    return {"success": True, "voice": updated}


@router.post("/voices/{voice_id}/retranscribe")
async def retranscribe_voice(request: Request, voice_id: int) -> dict[str, Any]:
    voice = await request.app.state.voice_store.get_voice_by_id(voice_id)
    if not voice:
        raise HTTPException(status_code=404, detail="Voice not found")
    updated = await request.app.state.voice_store.update_voice_settings(
        voice_id,
        {"reference_text": (voice.get("reference_text") or "")},
    )
    return {"success": True, "voice": updated}


@router.post("/voices/test")
async def test_voice(
    request: Request,
    voice_name: str = Form(...),
    user_id: int = Form(...),
    test_text: str = Form(...),
    cfg_strength: float | None = Form(default=None),
    speed_preset: float | None = Form(default=None),
) -> dict[str, Any]:
    _ = user_id, cfg_strength, speed_preset
    provider_request = {
        "text": test_text,
        "voice": voice_name,
        "tenant_id": "admin:test",
        "channel_name": "admin",
        "author": "admin",
        "user_id": user_id,
        "volume_level": 50.0,
        "metadata": {"admin_test": True},
    }
    result = await request.app.state.provider_synthesize(provider_request)
    return {
        "success": bool(result.get("success")),
        "audio_url": result.get("audio_url"),
        "voice": voice_name,
        "selected_voice": voice_name,
        "tts_type": "ai_f5",
        "duration": result.get("duration"),
        "error": result.get("error"),
    }


@router.get("/stats")
async def stats(request: Request) -> dict[str, Any]:
    stats_obj = await request.app.state.voice_store.stats()
    return {"success": True, **stats_obj.model_dump(mode="json")}

