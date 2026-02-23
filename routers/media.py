from fastapi import APIRouter, HTTPException, Depends
import logging
import os
from pathlib import Path
import re
from sqlalchemy.orm import Session
from database import get_db
from config import config
from database import Voice as VoiceModel
from auth import get_admin_user

router = APIRouter(tags=["media"])
logger = logging.getLogger(__name__)


VOICE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def _sanitize_voice_name(value: str) -> str:
    normalized = (value or "").strip()
    if not VOICE_NAME_RE.fullmatch(normalized):
        raise HTTPException(status_code=400, detail="Invalid voice name")
    return normalized


def _resolve_under_base(base_dir: Path, relative_name: str) -> Path:
    candidate = (base_dir / relative_name).resolve()
    base_resolved = base_dir.resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path")
    return candidate

@router.get("/audio/{voice_name}")
async def get_audio_file(voice_name: str):
    """Получить аудио файл голоса (для предпрослушивания)"""
    try:
        safe_voice_name = _sanitize_voice_name(voice_name)
        # Проверяем существование файла в voices
        # Это для старой логики, где voice_name мог быть именем файла
        voice_path = _resolve_under_base(config.voices_path, f"{safe_voice_name}.wav")
        if not voice_path.exists():
            # Пробуем найти как mp3
            voice_path = _resolve_under_base(config.voices_path, f"{safe_voice_name}.mp3")
            
        if not voice_path.exists():
             raise HTTPException(status_code=404, detail="Audio file not found")
             
        from fastapi.responses import FileResponse
        return FileResponse(voice_path)
        
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error serving audio file")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/audio/{voice_name}")
async def delete_audio_file(
    voice_name: str,
    current_user: dict = Depends(get_admin_user),
):
    """Удалить аудио файл (для тестовых файлов)"""
    # Ограничить использование только для админов или тестов
    try:
        safe_voice_name = _sanitize_voice_name(voice_name)
        voice_path = _resolve_under_base(config.audio_path, safe_voice_name)
        if voice_path.exists():
            os.remove(voice_path)
            return {"status": "success", "message": "File deleted"}
        raise HTTPException(status_code=404, detail="File not found")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error deleting audio file")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/voices/global")
async def get_global_voices(db: Session = Depends(get_db)):
    """Получить глобальные голоса (доступные всем)"""
    try:
        voices = db.query(VoiceModel).filter(
            VoiceModel.is_global.is_(True),
            VoiceModel.is_active.is_(True)
        ).all()
        
        return [
            {
                "id": voice.id,
                "name": voice.name,
                "voice_type": voice.voice_type,
                "is_global": voice.is_global,
                "is_active": voice.is_active,
                "cfg_strength": voice.cfg_strength,
                "speed_preset": voice.speed_preset,
                "reference_text": voice.reference_text,
                "created_at": voice.created_at.isoformat() if voice.created_at else None
            }
            for voice in voices
        ]
    except Exception:
        logger.exception("Error getting global voices")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/voices/{voice_id}")
async def get_voice_by_id(
    voice_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_admin_user),
):
    """Получить информацию о голосе по ID"""
    try:
        voice = db.query(VoiceModel).filter(VoiceModel.id == voice_id).first()
        
        if not voice:
            raise HTTPException(status_code=404, detail="Voice not found")
        
        return {
            "id": voice.id,
            "name": voice.name,
            "voice_type": voice.voice_type,
            "owner_id": voice.owner_id,
            "is_global": voice.is_global,
            "is_active": voice.is_active,
            "cfg_strength": voice.cfg_strength,
            "speed_preset": voice.speed_preset,
            "reference_text": voice.reference_text,
            "created_at": voice.created_at.isoformat() if voice.created_at else None
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error fetching voice")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/voices")
async def get_all_voices(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_admin_user),
):
    """Получить все голоса (для админки)"""
    try:
        voices = db.query(VoiceModel).all()
        return [
            {
                "id": voice.id,
                "name": voice.name,
                "voice_type": voice.voice_type,
                "owner_id": voice.owner_id,
                "is_global": voice.is_global,
                "is_active": voice.is_active,
                "cfg_strength": voice.cfg_strength,
                "speed_preset": voice.speed_preset,
                "created_at": voice.created_at.isoformat() if voice.created_at else None
            }
            for voice in voices
        ]
    except Exception:
        logger.exception("Error getting all voices")
        raise HTTPException(status_code=500, detail="Internal server error")


