from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException
import logging
import time
from tts_engine import tts_engine_manager
from gpu_worker_pool import gpu_worker_pool
from gpu_monitor import gpu_health_monitor
from gpu_integration import gpu_integration_service
from config import config
from auth import get_admin_user
from pydantic import BaseModel
router = APIRouter(tags=['system'])
logger = logging.getLogger(__name__)

class TtsConfigSchema(BaseModel):
    cfg_strength: float
    speed_preset: str

@router.get('/health')
async def health_check():
    """Проверка здоровья сервиса"""
    return {'status': 'healthy', 'timestamp': time.time(), 'tts_engine': 'ready' if tts_engine_manager.is_ready() else 'not_ready'}

@router.post('/engine/restart')
async def restart_engine(current_user: Dict[str, Any]=Depends(get_admin_user)):
    """Перезапустить TTS движок"""
    try:
        logger.info('Restarting TTS engine...')
        await tts_engine_manager.shutdown()
        await tts_engine_manager.initialize()
        logger.info('TTS engine restarted successfully')
        return {'message': 'TTS engine restarted successfully', 'status': 'ready'}
    except Exception:
        logger.exception('Error restarting TTS engine')
        raise HTTPException(status_code=500, detail='Failed to restart TTS engine')

@router.get('/config')
async def get_tts_config(current_user: Dict[str, Any]=Depends(get_admin_user)):
    """Получить текущие настройки TTS"""
    return {'cfg_strength': config.cfg_strength, 'speed_preset': 'normal'}

@router.put('/config')
async def update_tts_config(settings: TtsConfigSchema, current_user: Dict[str, Any]=Depends(get_admin_user)):
    """Обновить настраиваемые параметры TTS"""
    config.cfg_strength = settings.cfg_strength
    return {'status': 'success', 'message': 'Config updated'}

@router.get('/gpu/status')
async def get_gpu_status(current_user: Dict[str, Any]=Depends(get_admin_user)):
    """Получить статус GPU"""
    try:
        if not hasattr(gpu_worker_pool, 'running') or not gpu_worker_pool.running:
            return {'available': False, 'message': 'GPU Worker Pool not available'}
        stats = gpu_worker_pool.get_stats()
        health = gpu_health_monitor.get_health_summary()
        gpu_metrics = gpu_worker_pool.get_gpu_metrics()
        return {'available': True, 'running': gpu_worker_pool.running, 'stats': stats, 'health': health, 'gpu_metrics': gpu_metrics.__dict__ if gpu_metrics else None, 'timestamp': time.time()}
    except Exception:
        logger.exception('Error getting GPU status')
        raise HTTPException(status_code=500, detail='Internal server error')

@router.get('/gpu/health')
async def get_gpu_health_history(limit: int=50, current_user: Dict[str, Any]=Depends(get_admin_user)):
    """Получить историю здоровья GPU"""
    try:
        history = gpu_health_monitor.get_health_history(limit)
        return {'history': history, 'count': len(history), 'timestamp': time.time()}
    except Exception:
        logger.exception('Error getting GPU health history')
        raise HTTPException(status_code=500, detail='Internal server error')

@router.get('/gpu/stats')
async def get_gpu_integration_stats(current_user: Dict[str, Any]=Depends(get_admin_user)):
    """Получить статистику GPU интеграции"""
    try:
        stats = gpu_integration_service.get_stats()
        cached_tasks = gpu_integration_service.get_cached_tasks()
        return {'stats': stats, 'cached_tasks': cached_tasks, 'cached_tasks_count': len(cached_tasks), 'timestamp': time.time()}
    except Exception:
        logger.exception('Error getting GPU integration stats')
        raise HTTPException(status_code=500, detail='Internal server error')
