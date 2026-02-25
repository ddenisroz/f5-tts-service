from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile

from ..audio_processing import sanitize_voice_name
from ..auth import verify_api_key
from ..voice_uploads import prepare_uploaded_voice_file, transcribe_voice_file

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
    raw_name = name if name and name.strip() else file.filename or "global_voice"
    try:
        clean_name = sanitize_voice_name(raw_name)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    all_voices = await request.app.state.voice_store.list_all_voices()
    if any(
        str(item.get("voice_type") or "").strip().lower() == "global"
        and str(item.get("name", "")).strip().lower() == clean_name.lower()
        for item in all_voices
    ):
        raise HTTPException(status_code=400, detail=f"Voice with name '{clean_name}' already exists")

    target_path, reference_text = await prepare_uploaded_voice_file(
        request.app,
        upload=file,
        filename_prefix=f"global_{clean_name}",
    )
    try:
        voice = await request.app.state.voice_store.create_voice(
            name=clean_name,
            owner_id=None,
            voice_type="global",
            file_path=str(target_path),
            is_public=True,
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


@router.delete("/voices/{voice_id}")
async def delete_voice(request: Request, voice_id: int) -> dict[str, Any]:
    voice = await request.app.state.voice_store.get_voice_by_id(voice_id)
    file_path_raw = str((voice or {}).get("file_path") or "").strip()
    deleted = await request.app.state.voice_store.delete_voice(voice_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Voice not found")
    if file_path_raw:
        resolved = Path(file_path_raw).resolve()
        base = request.app.state.voice_files_dir.resolve()
        try:
            resolved.relative_to(base)
            resolved.unlink(missing_ok=True)
        except ValueError:
            pass
    return {"success": True}


@router.put("/voices/{voice_id}/rename")
async def rename_voice(request: Request, voice_id: int, new_name: str = Query(...)) -> dict[str, Any]:
    try:
        clean_name = sanitize_voice_name(new_name)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    voice = await request.app.state.voice_store.get_voice_by_id(voice_id)
    if not voice:
        raise HTTPException(status_code=404, detail="Voice not found")
    owner_id = int(voice.get("owner_id") or 0) if voice.get("owner_id") is not None else None
    voice_type = str(voice.get("voice_type") or "user").strip().lower()
    all_voices = await request.app.state.voice_store.list_all_voices()
    for item in all_voices:
        if int(item.get("id") or 0) == voice_id:
            continue
        if str(item.get("name", "")).strip().lower() != clean_name.lower():
            continue
        item_type = str(item.get("voice_type") or "user").strip().lower()
        item_owner = int(item.get("owner_id") or 0) if item.get("owner_id") is not None else None
        if voice_type == "global" and item_type == "global":
            raise HTTPException(status_code=400, detail=f"Voice with name '{clean_name}' already exists")
        if voice_type != "global" and item_owner == owner_id:
            raise HTTPException(status_code=400, detail=f"Voice with name '{clean_name}' already exists")
    try:
        updated = await request.app.state.voice_store.rename_voice(voice_id, clean_name)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
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
    if not request.app.state.transcriber.enabled:
        raise HTTPException(status_code=503, detail="Transcriber is disabled")
    voice = await request.app.state.voice_store.get_voice_by_id(voice_id)
    if not voice:
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


@router.post("/voices/{voice_id}/transcribe")
async def transcribe_voice(request: Request, voice_id: int) -> dict[str, Any]:
    return await retranscribe_voice(request, voice_id)


@router.post("/voices/test")
async def test_voice(
    request: Request,
    voice_name: str = Form(...),
    user_id: int = Form(...),
    test_text: str = Form(...),
    cfg_strength: float | None = Form(default=None),
    speed_preset: str | None = Form(default=None),
    remove_silence: bool = Form(default=False),
) -> dict[str, Any]:
    provider_request = {
        "text": test_text,
        "voice": voice_name,
        "tenant_id": "admin:test",
        "channel_name": "admin",
        "author": "admin",
        "user_id": user_id,
        "volume_level": 50.0,
        "cfg_strength": cfg_strength,
        "speed_preset": speed_preset,
        "remove_silence": remove_silence,
        "metadata": {
            "admin_test": True,
            "cfg_strength": cfg_strength,
            "speed_preset": speed_preset,
            "remove_silence": remove_silence,
        },
    }
    result = await request.app.state.provider_synthesize(provider_request)
    selected_voice = result.get("selected_voice") or result.get("voice") or voice_name
    return {
        "success": bool(result.get("success")),
        "audio_url": result.get("audio_url"),
        "voice": selected_voice,
        "selected_voice": selected_voice,
        "tts_type": "ai_f5",
        "duration": result.get("duration"),
        "error": result.get("error"),
    }


@router.get("/stats")
async def stats(request: Request, days: int = Query(default=7, ge=1, le=90)) -> dict[str, Any]:
    stats_obj = await request.app.state.voice_store.stats()
    limits_stats = await request.app.state.limits_store.get_global_stats(days=days)
    return {
        "success": True,
        **stats_obj.model_dump(mode="json"),
        "tts_limits_stats": limits_stats,
    }
