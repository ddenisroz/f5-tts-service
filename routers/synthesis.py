from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
import logging
import time
from typing import Optional
from tts_engine import tts_engine_manager
from async_tts_engine import async_tts_engine
from gpu_worker_pool import gpu_worker_pool
from auth import get_current_user_or_internal
router = APIRouter(tags=['synthesis'])
logger = logging.getLogger(__name__)

@router.post('/synthesize-channel')
async def synthesize_channel(request: dict, current_user: dict=Depends(get_current_user_or_internal)):
    """
    Синтезировать аудио для канала с учетом всех настроек пользователя.
    Вызывается из bot_service для обработки сообщений в чате.
    """
    try:
        channel_name = request.get('channel_name')
        text = request.get('text')
        author = request.get('author')
        user_id = request.get('user_id')
        volume_level = request.get('volume_level', 50)
        tts_settings = request.get('tts_settings', {})
        word_filter = request.get('word_filter', [])
        blocked_users = request.get('blocked_users', [])
        if not all([channel_name, text, author]):
            raise HTTPException(status_code=400, detail='Missing required parameters')
        logger.info(f'[MIC] [CHANNEL TTS] {channel_name} | {author}: {text[:50]}...')
        voice = tts_settings.get('voice', 'female_1') if tts_settings else 'female_1'
        logger.info(f'[TTS] [CHANNEL TTS] Using voice: {voice} (from tts_settings)')
        from tasks import generate_tts_task
        from celery.result import AsyncResult
        import asyncio
        import uuid
        message_id = str(uuid.uuid4())
        task = generate_tts_task.delay(text=text, voice=voice, user_id=user_id, platform='unknown', channel=channel_name, message_id=message_id)
        logger.info(f'[TTS] [CHANNEL TTS] Task submitted to Celery: {task.id}')
        max_retries = 60
        result = None
        for _ in range(max_retries):
            if task.ready():
                result = task.get()
                break
            await asyncio.sleep(0.5)
        if not result:
            logger.warning(f'[WARN] [CHANNEL TTS] Celery task {task.id} timed out')
            raise HTTPException(status_code=504, detail='Synthesis timed out')
        if result:
            logger.info(f'[OK] [CHANNEL TTS] Синтез успешен для {channel_name} (Task {task.id})')
            return {'success': True, 'selected_voice': result.get('voice', voice), 'audio_url': result.get('audio_url'), 'duration': 0, 'tts_type': 'f5'}
        else:
            logger.error(f'[ERROR] [CHANNEL TTS] Синтез не удался: Empty result')
            raise HTTPException(status_code=500, detail='Synthesis failed')
    except HTTPException:
        raise
    except Exception:
        logger.exception('[ERROR] [CHANNEL TTS] Ошибка')
        raise HTTPException(status_code=500, detail='Internal server error')

@router.post('/gpu/submit')
async def submit_gpu_task(text: str, voice: str='female_1', user_id: Optional[int]=None, priority: int=0, current_user: dict=Depends(get_current_user_or_internal)):
    """Отправить задачу напрямую в GPU Worker Pool"""
    try:
        if not hasattr(gpu_worker_pool, 'running') or not gpu_worker_pool.running:
            raise HTTPException(status_code=503, detail='GPU Worker Pool not available')
        task_id = await gpu_worker_pool.submit_task(text, voice, user_id, priority)
        return {'task_id': task_id, 'status': 'submitted', 'message': 'Task submitted to GPU Worker Pool', 'timestamp': time.time()}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error submitting GPU task')
        raise HTTPException(status_code=500, detail='Failed to submit GPU task')

@router.get('/gpu/task/{task_id}')
async def get_gpu_task_result(task_id: str, current_user: dict=Depends(get_current_user_or_internal)):
    """Получить результат задачи из GPU Worker Pool"""
    try:
        if not hasattr(gpu_worker_pool, 'running') or not gpu_worker_pool.running:
            raise HTTPException(status_code=503, detail='GPU Worker Pool not available')
        result = await gpu_worker_pool.get_task_result(task_id)
        if result is None:
            raise HTTPException(status_code=404, detail='Task not found or not completed')
        return {'task_id': task_id, 'result': result, 'timestamp': time.time()}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error getting GPU task result')
        raise HTTPException(status_code=500, detail='Failed to get task result')

@router.get('/task/{task_id}')
async def get_task_result(task_id: str, current_user: dict=Depends(get_current_user_or_internal)):
    """Получить результат асинхронной задачи (AsyncTTSEngine)"""
    try:
        status = await async_tts_engine.get_task_status(task_id)
        if not status:
            raise HTTPException(status_code=404, detail='Task not found')
        return status
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error getting task result')
        raise HTTPException(status_code=500, detail='Internal server error')
