"""API РґР»СЏ Р°РґРјРёРЅРёСЃС‚СЂРёСЂРѕРІР°РЅРёСЏ TTS Service"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body, Query, Response
from sqlalchemy.orm import Session
from database import get_db, Voice as VoiceModel
from tts_engine import tts_engine_manager
from file_manager import file_manager
from background_tasks import background_task_manager
from stats_service import stats_service
from auth import get_admin_user
from monitoring import tts_monitor
import logging
import os
from pathlib import Path
from typing import Dict, Any
import re
logger = logging.getLogger(__name__)
admin_router = APIRouter(tags=['admin'], dependencies=[Depends(get_admin_user)])
VOICE_NAME_RE = re.compile('^[0-9A-Za-z\\u0400-\\u04FF _-]{1,80}$')


def _set_legacy_deprecation_headers(response: Response) -> None:
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Wed, 31 Dec 2026 23:59:59 GMT"
    response.headers["Link"] = '</api/admin/voices>; rel=\"successor-version\"'

def _sanitize_voice_name(raw_name: str) -> str:
    normalized = (raw_name or '').strip()
    if not VOICE_NAME_RE.fullmatch(normalized):
        raise HTTPException(status_code=400, detail='Invalid voice name')
    return normalized

def _has_valid_audio_signature(file_path: str) -> bool:
    """Best-effort magic header validation for common audio containers/codecs."""
    try:
        with open(file_path, 'rb') as source:
            header = source.read(16)
    except OSError:
        return False
    if len(header) < 4:
        return False
    if header.startswith(b'RIFF') and len(header) >= 12 and (header[8:12] == b'WAVE'):
        return True
    if header.startswith(b'ID3') or (header[0] == 255 and header[1] & 224 == 224):
        return True
    if header.startswith(b'OggS'):
        return True
    if header.startswith(b'fLaC'):
        return True
    if len(header) >= 12 and header[4:8] == b'ftyp':
        return True
    if header.startswith(bytes.fromhex('3026B2758E66CF11')):
        return True
    if header.startswith(b'FORM') and len(header) >= 12 and (header[8:12] in {b'AIFF', b'AIFC'}):
        return True
    if header.startswith(b'.snd'):
        return True
    return False

@admin_router.get('/stats')
async def get_admin_stats(db: Session=Depends(get_db)):
    """РџРѕР»СѓС‡РёС‚СЊ СЃС‚Р°С‚РёСЃС‚РёРєСѓ РґР»СЏ Р°РґРјРёРЅРєРё"""
    try:
        stats = stats_service.get_system_overview()
        voices = db.query(VoiceModel).all()
        voice_stats = {'total_voices': len(voices), 'voices': [{'id': voice.id, 'name': voice.name, 'description': voice.description, 'is_active': voice.is_active, 'created_at': voice.created_at.isoformat() if voice.created_at else None} for voice in voices]}
        metrics = tts_monitor.get_metrics()
        return {'status': 'success', 'stats': stats, 'voices': voice_stats, 'metrics': metrics}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Admin stats error')
        raise HTTPException(status_code=500, detail='Internal server error')

@admin_router.get('/voices')
async def get_voices(db: Session=Depends(get_db)):
    """РџРѕР»СѓС‡РёС‚СЊ СЃРїРёСЃРѕРє РіРѕР»РѕСЃРѕРІ"""
    try:
        voices = db.query(VoiceModel).all()
        return {'status': 'success', 'voices': [{'id': voice.id, 'name': voice.name, 'voice_type': voice.voice_type, 'owner_id': voice.owner_id, 'is_active': voice.is_active, 'file_path': voice.file_path, 'reference_text': voice.reference_text, 'cfg_strength': voice.cfg_strength, 'speed_preset': voice.speed_preset, 'created_at': voice.created_at.isoformat() if voice.created_at else None} for voice in voices]}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Get voices error')
        raise HTTPException(status_code=500, detail='Internal server error')

@admin_router.post('/voices/{voice_id}/toggle')
async def toggle_voice(voice_id: int, db: Session=Depends(get_db)):
    """Р’РєР»СЋС‡РёС‚СЊ/РІС‹РєР»СЋС‡РёС‚СЊ РіРѕР»РѕСЃ"""
    try:
        voice = db.query(VoiceModel).filter(VoiceModel.id == voice_id).first()
        if not voice:
            raise HTTPException(status_code=404, detail='Voice not found')
        voice.is_active = not voice.is_active
        db.commit()
        return {'status': 'success', 'message': f"Voice {voice.name} {('enabled' if voice.is_active else 'disabled')}", 'voice': {'id': voice.id, 'name': voice.name, 'is_active': voice.is_active}}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Toggle voice error')
        db.rollback()
        raise HTTPException(status_code=500, detail='Internal server error')

@admin_router.post('/voices/upload')
async def upload_voice(file: UploadFile=File(...), name: str=None, db: Session=Depends(get_db), current_user: Dict[str, Any]=Depends(get_admin_user)):
    """Р—Р°РіСЂСѓР·РёС‚СЊ РЅРѕРІС‹Р№ РіРѕР»РѕСЃ РґР»СЏ AI TTS СЃ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРѕР№ РєРѕРЅРІРµСЂС‚Р°С†РёРµР№ Рё С‚СЂР°РЅСЃРєСЂРёР±Р°С†РёРµР№"""
    import tempfile
    temp_input_path = None
    temp_converted_path = None
    final_voice_path = None
    try:
        allowed_extensions = ['.wav', '.mp3', '.ogg', '.flac', '.m4a', '.aac', '.wma', '.aiff', '.au']
        file_extension = os.path.splitext(file.filename)[1].lower()
        if file_extension not in allowed_extensions:
            raise HTTPException(status_code=400, detail=f"РќРµРїРѕРґРґРµСЂР¶РёРІР°РµРјС‹Р№ С„РѕСЂРјР°С‚ С„Р°Р№Р»Р°. Р Р°Р·СЂРµС€РµРЅС‹: {', '.join(allowed_extensions)}")
        voice_name = _sanitize_voice_name(name or os.path.splitext(file.filename)[0])
        existing_voice = db.query(VoiceModel).filter(VoiceModel.name == voice_name).first()
        if existing_voice:
            raise HTTPException(status_code=400, detail=f"Р“РѕР»РѕСЃ СЃ РёРјРµРЅРµРј '{voice_name}' СѓР¶Рµ СЃСѓС‰РµСЃС‚РІСѓРµС‚")
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
            contents = await file.read()
            temp_file.write(contents)
            temp_input_path = temp_file.name
        if not _has_valid_audio_signature(temp_input_path):
            raise HTTPException(status_code=400, detail='Invalid audio file signature')
        logger.info(f'[RECEIVE] Voice file uploaded to temp: {temp_input_path}')
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_converted_file:
            temp_converted_path = temp_converted_file.name
        from async_audio_converter import AsyncAudioConverter
        converter = AsyncAudioConverter(max_workers=1)
        await converter.start_workers()
        try:
            success = converter._convert_audio_sync(temp_input_path, temp_converted_path, 'upload_task')
            if not success:
                raise Exception('Audio conversion failed')
            logger.info(f'[OK] Audio converted to WAV: {temp_converted_path}')
        finally:
            await converter.stop_workers()
        reference_text = ''
        try:
            from tts_engine import tts_engine_manager
            if tts_engine_manager.transcriber:
                reference_text = tts_engine_manager.transcribe(temp_converted_path)
                logger.info(f"[OK] Audio transcribed: '{reference_text[:50]}...'")
            else:
                logger.warning('[WARN] Transcriber not available, skipping transcription')
        except Exception:
            logger.exception('[WARN] Transcription failed, continuing without reference text')
        voices_dir = Path('audio/voices/global')
        voices_dir.mkdir(parents=True, exist_ok=True)
        safe_filename = f'{voice_name}.wav'
        final_voice_path = voices_dir / safe_filename
        import shutil
        shutil.copy2(temp_converted_path, final_voice_path)
        logger.info(f'[OK] Voice saved: {final_voice_path}')
        from config import config
        new_voice = VoiceModel(name=voice_name, voice_type='global', file_path=str(final_voice_path), reference_text=reference_text or None, is_active=True, is_global=True, owner_id=None, cfg_strength=config.cfg_strength, speed_preset='normal')
        db.add(new_voice)
        db.commit()
        db.refresh(new_voice)
        logger.info(f"[OK] Global voice '{voice_name}' uploaded successfully by admin user {current_user.get('user_id')} (Voice ID: {new_voice.id})")
        return {'status': 'success', 'message': f"Р“РѕР»РѕСЃ '{voice_name}' СѓСЃРїРµС€РЅРѕ Р·Р°РіСЂСѓР¶РµРЅ, РєРѕРЅРІРµСЂС‚РёСЂРѕРІР°РЅ РІ WAV Рё С‚СЂР°РЅСЃРєСЂРёР±РёСЂРѕРІР°РЅ", 'voice': {'id': new_voice.id, 'name': new_voice.name, 'voice_type': new_voice.voice_type, 'is_active': new_voice.is_active, 'file_path': str(final_voice_path), 'reference_text': reference_text[:100] + '...' if reference_text and len(reference_text) > 100 else reference_text, 'format': 'WAV 48kHz Mono 16-bit'}}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Voice upload error')
        db.rollback()
        if final_voice_path and Path(final_voice_path).exists():
            Path(final_voice_path).unlink()
        raise HTTPException(status_code=500, detail='Internal server error')
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

@admin_router.post('/voices/{voice_id}/retranscribe')
async def retranscribe_voice(voice_id: int, db: Session=Depends(get_db)):
    """РџРµСЂРµС‚СЂР°РЅСЃРєСЂРёР±РёСЂРѕРІР°С‚СЊ РіРѕР»РѕСЃ - РёР·РІР»РµС‡СЊ reference_text РёР· Р°СѓРґРёРѕС„Р°Р№Р»Р° Р·Р°РЅРѕРІРѕ"""
    try:
        voice = db.query(VoiceModel).filter(VoiceModel.id == voice_id).first()
        if not voice:
            raise HTTPException(status_code=404, detail='Р“РѕР»РѕСЃ РЅРµ РЅР°Р№РґРµРЅ')
        if not voice.file_path or not os.path.exists(voice.file_path):
            raise HTTPException(status_code=404, detail='РђСѓРґРёРѕС„Р°Р№Р» РЅРµ РЅР°Р№РґРµРЅ')
        logger.info(f'[REFRESH] Starting retranscription for voice {voice_id} ({voice.name})')
        reference_text = ''
        try:
            from tts_engine import tts_engine_manager
            if tts_engine_manager.transcriber:
                reference_text = tts_engine_manager.transcribe(voice.file_path)
                logger.info(f"[OK] Retranscribed: '{reference_text[:50]}...'")
            else:
                raise Exception('Transcriber not available')
        except Exception:
            logger.exception('[ERROR] Transcription failed')
            raise HTTPException(status_code=500, detail='Internal server error')
        voice.reference_text = reference_text
        db.commit()
        db.refresh(voice)
        logger.info(f'[OK] Voice {voice_id} retranscribed successfully')
        return {'status': 'success', 'message': f"Р“РѕР»РѕСЃ '{voice.name}' СѓСЃРїРµС€РЅРѕ РїРµСЂРµС‚СЂР°РЅСЃРєСЂРёР±РёСЂРѕРІР°РЅ", 'reference_text': reference_text, 'voice_id': voice_id}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Retranscribe error')
        raise HTTPException(status_code=500, detail='Internal server error')

@admin_router.post('/voices/test')
async def test_voice(voice_name: str=Form(...), user_id: int=Form(...), test_text: str=Form(...), cfg_strength: float=Form(None), speed_preset: str=Form(None), db: Session=Depends(get_db)):
    """РўРµСЃС‚РёСЂРѕРІР°С‚СЊ РіРѕР»РѕСЃ СЃ Р·Р°РґР°РЅРЅС‹Рј С‚РµРєСЃС‚РѕРј Рё РЅР°СЃС‚СЂРѕР№РєР°РјРё"""
    from pathlib import Path
    try:
        if not voice_name or not test_text:
            raise HTTPException(status_code=400, detail='voice_name and test_text are required')
        voice = db.query(VoiceModel).filter(VoiceModel.name == voice_name).first()
        if not voice:
            raise HTTPException(status_code=404, detail=f"Voice '{voice_name}' not found")
        if voice.owner_id and user_id and (voice.owner_id != user_id):
            raise HTTPException(status_code=403, detail='Access denied')
        logger.info(f"[TTS] Testing voice '{voice_name}' with text: '{test_text[:50]}...'")
        cfg = cfg_strength if cfg_strength is not None else voice.cfg_strength
        speed = speed_preset if speed_preset is not None else voice.speed_preset
        result = await tts_engine_manager.synthesize_speech_async(text=test_text, voice=voice_name, user_id=user_id, channel_name='test', author='admin', volume=50.0, tts_settings={'voice_settings': {'cfg_strength': cfg, 'speed_preset': speed}})
        if not result.get('success'):
            raise HTTPException(status_code=500, detail='Synthesis failed')
        audio_url = result.get('audio_url')
        audio_path = result.get('audio_path')
        if audio_url:
            logger.info(f'[OK] Test synthesis completed: {audio_url}')
            return {'status': 'success', 'audio_url': audio_url, 'message': 'Test synthesis completed successfully'}
        if audio_path:
            from config import config
            audio_path_obj = Path(audio_path)
            try:
                abs_audio_path = config.audio_path.resolve()
                abs_audio_file = audio_path_obj.resolve()
                try:
                    relative_path = abs_audio_file.relative_to(abs_audio_path)
                    audio_url = f'/audio/{relative_path.as_posix()}'
                except ValueError:
                    audio_url = f'/audio/{audio_path_obj.name}'
                logger.info(f'[OK] Test synthesis completed: {audio_url}')
                return {'status': 'success', 'audio_url': audio_url, 'message': 'Test synthesis completed successfully'}
            except Exception:
                logger.exception('Error processing audio path')
                raise HTTPException(status_code=500, detail='Internal server error')
        raise HTTPException(status_code=500, detail='Audio file not generated')
    except HTTPException:
        raise
    except Exception:
        logger.exception('Test voice error')
        raise HTTPException(status_code=500, detail='Internal server error')

@admin_router.delete('/legacy/voices/{voice_id}')
async def delete_legacy_voice(voice_id: int, response: Response, db: Session=Depends(get_db)):
    """РЈРґР°Р»РёС‚СЊ РіРѕР»РѕСЃ"""
    try:
        _set_legacy_deprecation_headers(response)
        voice = db.query(VoiceModel).filter(VoiceModel.id == voice_id).first()
        if not voice:
            raise HTTPException(status_code=404, detail='Voice not found')
        if voice.file_path and Path(voice.file_path).exists():
            try:
                Path(voice.file_path).unlink()
                logger.info(f'Voice file deleted: {voice.file_path}')
            except Exception:
                logger.exception('Failed to delete voice file')
        db.delete(voice)
        db.commit()
        logger.info(f"Voice '{voice.name}' (ID: {voice_id}) deleted successfully")
        return {'status': 'success', 'message': f"Р“РѕР»РѕСЃ '{voice.name}' СѓСЃРїРµС€РЅРѕ СѓРґР°Р»С‘РЅ"}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Voice delete error')
        db.rollback()
        raise HTTPException(status_code=500, detail='Internal server error')

@admin_router.put('/legacy/voices/{voice_id}/settings')
async def update_legacy_voice_settings(voice_id: int, response: Response, settings: dict=Body(...), db: Session=Depends(get_db)):
    """РћР±РЅРѕРІРёС‚СЊ РЅР°СЃС‚СЂРѕР№РєРё РіРѕР»РѕСЃР° (reference_text, cfg_strength, speed_preset)"""
    try:
        _set_legacy_deprecation_headers(response)
        voice = db.query(VoiceModel).filter(VoiceModel.id == voice_id).first()
        if not voice:
            raise HTTPException(status_code=404, detail='Р“РѕР»РѕСЃ РЅРµ РЅР°Р№РґРµРЅ')
        if 'reference_text' in settings:
            voice.reference_text = settings['reference_text']
        if 'cfg_strength' in settings:
            voice.cfg_strength = settings['cfg_strength']
        if 'speed_preset' in settings:
            voice.speed_preset = settings['speed_preset']
        db.commit()
        db.refresh(voice)
        logger.info(f'[OK] Voice {voice_id} settings updated')
        return {'status': 'success', 'message': 'РќР°СЃС‚СЂРѕР№РєРё РіРѕР»РѕСЃР° РѕР±РЅРѕРІР»РµРЅС‹', 'voice': {'id': voice.id, 'name': voice.name, 'reference_text': voice.reference_text, 'cfg_strength': voice.cfg_strength, 'speed_preset': voice.speed_preset}}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Update voice settings error')
        db.rollback()
        raise HTTPException(status_code=500, detail='Internal server error')

@admin_router.put('/legacy/voices/{voice_id}/rename')
async def rename_legacy_voice(voice_id: int, response: Response, new_name: str=Query(..., description='РќРѕРІРѕРµ РёРјСЏ РіРѕР»РѕСЃР°'), db: Session=Depends(get_db)):
    """РџРµСЂРµРёРјРµРЅРѕРІР°С‚СЊ РіРѕР»РѕСЃ"""
    try:
        _set_legacy_deprecation_headers(response)
        voice = db.query(VoiceModel).filter(VoiceModel.id == voice_id).first()
        if not voice:
            raise HTTPException(status_code=404, detail='Voice not found')
        sanitized_new_name = _sanitize_voice_name(new_name)
        existing_voice = db.query(VoiceModel).filter(VoiceModel.name == sanitized_new_name, VoiceModel.id != voice_id).first()
        if existing_voice:
            raise HTTPException(status_code=400, detail=f"Р“РѕР»РѕСЃ СЃ РёРјРµРЅРµРј '{sanitized_new_name}' СѓР¶Рµ СЃСѓС‰РµСЃС‚РІСѓРµС‚")
        old_name = voice.name
        voice.name = sanitized_new_name
        db.commit()
        logger.info(f"Voice renamed from '{old_name}' to '{sanitized_new_name}' (ID: {voice_id})")
        return {'status': 'success', 'message': f"Р“РѕР»РѕСЃ РїРµСЂРµРёРјРµРЅРѕРІР°РЅ: '{old_name}' в†’ '{sanitized_new_name}'", 'voice': {'id': voice.id, 'name': voice.name}}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Voice rename error')
        db.rollback()
        raise HTTPException(status_code=500, detail='Internal server error')

@admin_router.get('/system/status')
async def get_system_status():
    """РџРѕР»СѓС‡РёС‚СЊ СЃС‚Р°С‚СѓСЃ СЃРёСЃС‚РµРјС‹"""
    try:
        return {'status': 'success', 'system': {'tts_engine': tts_engine_manager.is_initialized(), 'file_manager': file_manager.is_initialized(), 'background_tasks': background_task_manager.is_running(), 'monitoring': tts_monitor.is_running()}}
    except Exception:
        logger.exception('System status error')
        raise HTTPException(status_code=500, detail='Internal server error')

@admin_router.post('/system/restart')
async def restart_system():
    """РџРµСЂРµР·Р°РїСѓСЃС‚РёС‚СЊ СЃРёСЃС‚РµРјСѓ (Р·Р°РіР»СѓС€РєР°)"""
    try:
        logger.warning('System restart requested')
        return {'status': 'success', 'message': 'Restart command sent (not implemented in development)'}
    except Exception:
        logger.exception('System restart error')
        raise HTTPException(status_code=500, detail='Internal server error')

@admin_router.put('/voices/{voice_id}/settings')
async def update_voice_settings(voice_id: int, settings: dict, current_user: Dict[str, Any]=Depends(get_admin_user), db: Session=Depends(get_db)):
    """Update settings for a voice (admin only)"""
    try:
        voice = db.query(VoiceModel).filter(VoiceModel.id == voice_id).first()
        if not voice:
            raise HTTPException(status_code=404, detail='Voice not found')
        if 'cfg_strength' in settings:
            voice.cfg_strength = settings['cfg_strength']
        if 'speed_preset' in settings:
            voice.speed_preset = settings['speed_preset']
        if 'reference_text' in settings:
            voice.reference_text = settings['reference_text']
        db.commit()
        db.refresh(voice)
        logger.info(f'[OK] Admin updated voice {voice_id} settings')
        return {'success': True, 'message': 'Voice settings updated', 'settings': {'cfg_strength': voice.cfg_strength, 'speed_preset': voice.speed_preset, 'reference_text': voice.reference_text}}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error updating voice settings')
        db.rollback()
        raise HTTPException(status_code=500, detail='Internal server error')

@admin_router.delete('/voices/{voice_id}')
async def delete_voice(voice_id: int, current_user: Dict[str, Any]=Depends(get_admin_user), db: Session=Depends(get_db)):
    """Delete a voice (admin only)"""
    try:
        voice = db.query(VoiceModel).filter(VoiceModel.id == voice_id).first()
        if not voice:
            raise HTTPException(status_code=404, detail='Voice not found')
        if voice.file_path and os.path.exists(voice.file_path):
            try:
                os.remove(voice.file_path)
                logger.info(f'[OK] Deleted voice file: {voice.file_path}')
            except Exception:
                logger.exception('[WARN] Failed to delete voice file')
        db.delete(voice)
        db.commit()
        logger.info(f'[OK] Admin deleted voice {voice_id}')
        return {'success': True, 'message': 'Voice deleted successfully'}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error deleting voice')
        db.rollback()
        raise HTTPException(status_code=500, detail='Internal server error')

@admin_router.put('/voices/{voice_id}/rename')
async def rename_voice_endpoint(voice_id: int, new_name: str, current_user: Dict[str, Any]=Depends(get_admin_user), db: Session=Depends(get_db)):
    """Rename a voice (admin only)"""
    try:
        voice = db.query(VoiceModel).filter(VoiceModel.id == voice_id).first()
        if not voice:
            raise HTTPException(status_code=404, detail='Voice not found')
        sanitized_new_name = _sanitize_voice_name(new_name)
        existing_voice = db.query(VoiceModel).filter(VoiceModel.name == sanitized_new_name, VoiceModel.id != voice_id).first()
        if existing_voice:
            raise HTTPException(status_code=400, detail=f"Voice with name '{sanitized_new_name}' already exists")
        old_name = voice.name
        voice.name = sanitized_new_name
        db.commit()
        logger.info(f"[OK] Admin renamed voice {voice_id} from '{old_name}' to '{sanitized_new_name}'")
        return {'success': True, 'message': f"Voice renamed from '{old_name}' to '{sanitized_new_name}'", 'new_name': sanitized_new_name}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error renaming voice')
        db.rollback()
        raise HTTPException(status_code=500, detail='Internal server error')

