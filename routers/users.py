from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, UploadFile, File, Form, Query
import logging
import os
import shutil
import tempfile
import re
from pathlib import Path
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session
from database import get_db
from database import Voice as VoiceModel
from config import config
from tts_engine import tts_engine_manager
from async_audio_converter import AsyncAudioConverter
from tts_limits_service import tts_limits_service
from auth import get_current_user_or_internal

router = APIRouter(tags=["users"])
logger = logging.getLogger(__name__)


def _get_actor_user_id(current_user: Dict[str, Any]) -> int:
    user_id = current_user.get("user_id", current_user.get("id"))
    if not isinstance(user_id, int):
        raise HTTPException(status_code=401, detail="Invalid authentication payload")
    return user_id


def _ensure_user_access(current_user: Dict[str, Any], target_user_id: int) -> None:
    actor_user_id = _get_actor_user_id(current_user)
    if current_user.get("role") == "admin" or current_user.get("is_admin"):
        return
    if actor_user_id != target_user_id:
        raise HTTPException(status_code=403, detail="Access denied")


def _sanitize_voice_name(raw_name: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-zА-Яа-яЁё _-]", "", raw_name or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Invalid voice name")
    if len(cleaned) > 80:
        cleaned = cleaned[:80].rstrip()
    return cleaned


def _has_valid_audio_signature(file_path: str) -> bool:
    """Best-effort magic header validation for common audio containers/codecs."""
    try:
        with open(file_path, "rb") as source:
            header = source.read(16)
    except OSError:
        return False

    if len(header) < 4:
        return False

    # WAV / RIFF
    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WAVE":
        return True
    # MP3 (ID3 tag) or MPEG frame sync
    if header.startswith(b"ID3") or (header[0] == 0xFF and (header[1] & 0xE0) == 0xE0):
        return True
    # OGG
    if header.startswith(b"OggS"):
        return True
    # FLAC
    if header.startswith(b"fLaC"):
        return True
    # MP4/M4A family
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return True
    # WMA/ASF
    if header.startswith(bytes.fromhex("3026B2758E66CF11")):
        return True
    # AIFF
    if header.startswith(b"FORM") and len(header) >= 12 and header[8:12] in {b"AIFF", b"AIFC"}:
        return True
    # AU
    if header.startswith(b".snd"):
        return True

    return False

# --- VOICE MANAGEMENT ---

@router.get("/user/voices/{user_id}")
async def get_user_voices(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user_or_internal),
):
    """Получить голоса пользователя"""
    try:
        _ensure_user_access(current_user, user_id)
        voices = db.query(VoiceModel).filter(
            VoiceModel.owner_id == user_id,
            VoiceModel.is_active.is_(True)
        ).all()
        
        return [
            {
                "id": voice.id,
                "name": voice.name,
                "voice_type": voice.voice_type,
                "is_active": voice.is_active,
                "cfg_strength": voice.cfg_strength,
                "speed_preset": voice.speed_preset,
                "reference_text": voice.reference_text,
                "created_at": voice.created_at.isoformat() if voice.created_at else None
            }
            for voice in voices
        ]
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting user voices")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/user/voices/upload")
async def upload_user_voice(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    voice_name: str = Form(...),
    user_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user_or_internal),
):
    """Загрузить пользовательский голос с автоматической конвертацией и транскрибацией"""
    temp_input_path = None
    temp_converted_path = None
    final_voice_path = None
    
    try:
        _ensure_user_access(current_user, user_id)
        voice_name = _sanitize_voice_name(voice_name)

        # Проверка типа файла
        allowed_extensions = ['.wav', '.mp3', '.ogg', '.flac', '.m4a', '.aac', '.wma', '.aiff', '.au']
        file_extension = os.path.splitext(file.filename)[1].lower()
        
        if file_extension not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Неподдерживаемый формат файла. Разрешены: {', '.join(allowed_extensions)}"
            )
        
        # Проверка дубликатов
        existing_voice = db.query(VoiceModel).filter(
            VoiceModel.name == voice_name,
            VoiceModel.owner_id == user_id
        ).first()
        if existing_voice:
            raise HTTPException(status_code=400, detail=f"Голос с именем '{voice_name}' уже существует")
        
        # Сохраняем загруженный файл во временную директорию
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_input_path = temp_file.name

        if not _has_valid_audio_signature(temp_input_path):
            raise HTTPException(status_code=400, detail="Invalid audio file signature")
        
        logger.info(f"[RECEIVE] User voice uploaded to temp: {temp_input_path}")
        
        # Конвертируем в WAV с требованиями F5-TTS
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_converted_file:
            temp_converted_path = temp_converted_file.name
        
        converter = AsyncAudioConverter(max_workers=1)
        await converter.start_workers()
        
        try:
            success = converter._convert_audio_sync(temp_input_path, temp_converted_path, "user_upload_task")
            if not success:
                raise Exception("Audio conversion failed")
            
            logger.info(f"[OK] Audio converted to WAV: {temp_converted_path}")
        finally:
            await converter.stop_workers()
        
        # Автоматическая транскрибация
        reference_text = ""
        try:
            if tts_engine_manager.transcriber:
                reference_text = tts_engine_manager.transcribe(temp_converted_path)
                logger.info(f"[OK] Audio transcribed: '{reference_text[:50]}...'")
            else:
                logger.warning("[WARN] Transcriber not available, skipping transcription")
        except Exception:
            logger.warning("[WARN] Transcription failed, continuing without reference text", exc_info=True)
        
        # Сохраняем в финальную директорию
        voices_dir = config.user_voices_path / str(user_id)
        voices_dir.mkdir(parents=True, exist_ok=True)
        
        # ВСЕГДА сохраняем как WAV
        safe_filename = f"{voice_name}.wav"
        final_voice_path = voices_dir / safe_filename
        
        # Копируем конвертированный файл
        shutil.copy2(temp_converted_path, final_voice_path)
        
        logger.info(f"[OK] User voice saved: {final_voice_path}")
        
        # Создаём запись в БД
        new_voice = VoiceModel(
            name=voice_name,
            voice_type='user',
            file_path=str(final_voice_path),
            reference_text=reference_text or None,
            owner_id=user_id,
            is_active=True,
            is_global=False,
            cfg_strength=config.cfg_strength,
            speed_preset='normal'
        )
        db.add(new_voice)
        db.commit()
        db.refresh(new_voice)
        
        logger.info(f"[OK] User voice '{voice_name}' uploaded for user {user_id} (ID: {new_voice.id})")
        
        return {
            "status": "success",
            "message": f"Голос '{voice_name}' успешно загружен, конвертирован и транскрибирован",
            "voice": {
                "id": new_voice.id,
                "name": new_voice.name,
                "voice_type": new_voice.voice_type,
                "is_active": new_voice.is_active,
                "file_path": str(final_voice_path),
                "reference_text": reference_text[:100] + "..." if reference_text and len(reference_text) > 100 else reference_text,
                "format": "WAV 48kHz Mono 16-bit"
            }
        }
        
    except HTTPException:
        raise
    except Exception:
        logger.exception("User voice upload error")
        db.rollback()
        
        if final_voice_path and Path(final_voice_path).exists():
            Path(final_voice_path).unlink()
        
        raise HTTPException(status_code=500, detail="Internal server error")
    
    finally:
        if temp_input_path and os.path.exists(temp_input_path):
            try:
                os.unlink(temp_input_path)
            except OSError:
                pass
        
        if temp_converted_path and os.path.exists(temp_converted_path):
            try:
                os.unlink(temp_converted_path)
            except OSError:
                pass

@router.delete("/user/voices/{voice_id}")
async def delete_user_voice(
    voice_id: int,
    user_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user_or_internal),
):
    """Удалить пользовательский голос"""
    try:
        _ensure_user_access(current_user, user_id)
        voice = db.query(VoiceModel).filter(
            VoiceModel.id == voice_id,
            VoiceModel.owner_id == user_id,
            VoiceModel.is_global == False
        ).first()
        
        if not voice:
            raise HTTPException(
                status_code=404,
                detail="Voice not found or access denied"
            )
        
        if voice.file_path and os.path.exists(voice.file_path):
            try:
                os.remove(voice.file_path)
                logger.info(f"[OK] Deleted voice file: {voice.file_path}")
            except Exception:
                logger.warning("[WARN] Failed to delete voice file", exc_info=True)
        
        db.delete(voice)
        db.commit()
        
        return {
            "success": True,
            "message": "Voice deleted successfully"
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error deleting voice")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

@router.put("/user/voices/{voice_id}/rename")
async def rename_user_voice(
    voice_id: int, 
    user_id: int = Query(..., description="User ID"),
    new_name: str = Form(...), 
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user_or_internal),
):
    """Переименовать пользовательский голос"""
    try:
        _ensure_user_access(current_user, user_id)
        new_name = _sanitize_voice_name(new_name)
        voice = db.query(VoiceModel).filter(
            VoiceModel.id == voice_id,
            VoiceModel.owner_id == user_id
        ).first()
        
        if not voice:
            raise HTTPException(status_code=404, detail="Voice not found or access denied")
        
        existing_voice = db.query(VoiceModel).filter(
            VoiceModel.name == new_name,
            VoiceModel.owner_id == user_id,
            VoiceModel.id != voice_id
        ).first()
        if existing_voice:
            raise HTTPException(status_code=400, detail=f"Voice with name '{new_name}' already exists")
        
        voice.name = new_name
        db.commit()
        
        return {"status": "success", "message": "Voice renamed successfully"}
        
    except HTTPException:
        raise
    except Exception:
        logger.exception("Rename voice error")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/user/voices/{voice_id}/transcribe")
async def transcribe_user_voice(
    voice_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user_or_internal),
):
    """Транскрибировать пользовательский голос (обновить reference text)"""
    try:
        _ensure_user_access(current_user, user_id)
        voice = db.query(VoiceModel).filter(
            VoiceModel.id == voice_id,
            VoiceModel.owner_id == user_id
        ).first()
        
        if not voice:
            raise HTTPException(status_code=404, detail="Voice not found or access denied")
        
        if not voice.file_path or not os.path.exists(voice.file_path):
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        logger.info(f"[REFRESH] Transcribing user voice {voice_id} ({voice.name})")
        
        reference_text = ""
        try:
            if tts_engine_manager.transcriber:
                reference_text = tts_engine_manager.transcribe(voice.file_path)
                logger.info(f"[OK] Transcribed: '{reference_text[:50]}...'")
            else:
                raise Exception("Transcriber not available")
        except Exception:
            logger.exception("[ERROR] Transcription failed")
            raise HTTPException(status_code=500, detail="Internal server error")
        
        voice.reference_text = reference_text
        db.commit()
        db.refresh(voice)
        
        return {
            "status": "success",
            "message": "Voice transcribed successfully",
            "reference_text": reference_text
        }
        
    except HTTPException:
        raise
    except Exception:
        logger.exception("Transcribe voice error")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/user/voices/{voice_id}/retranscribe")
async def retranscribe_user_voice(
    voice_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user_or_internal),
):
    """Перетранскрибировать (алиас для transcribe)"""
    return await transcribe_user_voice(voice_id, user_id, db, current_user)

@router.put("/user/voices/{voice_id}/settings")
async def update_user_voice_settings(
    voice_id: int,
    settings: dict, # Expecting {cfg_strength, speed_preset} and maybe user_id in query or body? 
                    # Original endpoint had user_id in body for update_user_voice_settings_endpoint vs query for update_user_voice_settings
    user_id: Optional[int] = Query(None), # Trying to support both signatures if possible or stick to one
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user_or_internal),
):
    """Обновить настройки пользовательского голоса"""
    try:
        # Determine user_id: passed in query OR inside settings dict? 
        # Ideally it should be authenticated. The original code was messy:
        # One endpoint took user_id as argument (body), another as query.
        # Let's check permissions. If user_id provided, verify ownership.
        
        target_user_id = user_id or settings.get('user_id')
        
        voice = db.query(VoiceModel).filter(VoiceModel.id == voice_id).first()
        
        if not voice:
            raise HTTPException(status_code=404, detail="Voice not found")
            
        if target_user_id and voice.owner_id != int(target_user_id):
            raise HTTPException(status_code=403, detail="Access denied")

        _ensure_user_access(current_user, voice.owner_id)
        
        if voice.is_global:
            raise HTTPException(
                status_code=403,
                detail="Cannot modify global voice settings. Use personal settings instead."
            )
        
        if 'reference_text' in settings:
            voice.reference_text = settings['reference_text']
        if 'cfg_strength' in settings:
            voice.cfg_strength = settings['cfg_strength']
        if 'speed_preset' in settings:
            voice.speed_preset = settings['speed_preset']
        
        db.commit()
        db.refresh(voice)
        
        return {
            "success": True,
            "message": "Voice settings updated",
            "settings": {
                "cfg_strength": voice.cfg_strength,
                "speed_preset": voice.speed_preset,
                "reference_text": voice.reference_text
            }
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error updating voice settings")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

# --- LIMITS & STATS ---

from models import UserTTSLimitsSchema

@router.get("/user/tts-limits/{user_id}")
async def get_user_tts_limits(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user_or_internal),
):
    """Получить настройки и лимиты TTS пользователя"""
    try:
        _ensure_user_access(current_user, user_id)
        limits = tts_limits_service.get_user_limits(user_id, db)
        return limits
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting TTS limits")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.put("/user/tts-limits/{user_id}")
async def update_user_tts_limits(
    user_id: int, 
    limits: UserTTSLimitsSchema, 
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user_or_internal),
):
    """Обновить настройки и лимиты TTS пользователя"""
    try:
        _ensure_user_access(current_user, user_id)
        updated_limits = tts_limits_service.update_user_limits(user_id, limits, db)
        return updated_limits
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error updating TTS limits")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/user/tts-stats/{user_id}")
async def get_user_tts_stats(
    user_id: int,
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user_or_internal),
):
    """Получить статистику использования TTS пользователем"""
    try:
        _ensure_user_access(current_user, user_id)
        stats = tts_limits_service.get_user_stats(user_id, days, db)
        return stats
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting user TTS stats")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/tts/stats/global")
async def get_global_tts_stats(
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user_or_internal),
):
    """Получить глобальную статистику TTS"""
    try:
        if not (current_user.get("role") == "admin" or current_user.get("is_admin")):
            raise HTTPException(status_code=403, detail="Admin access required")
        stats = tts_limits_service.get_global_stats(days, db)
        return stats
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting global TTS stats")
        raise HTTPException(status_code=500, detail="Internal server error")



