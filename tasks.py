import asyncio
from celery.utils.log import get_task_logger
import os
from pathlib import Path
import sys

# Add project root to path
service_root = Path(__file__).resolve().parent
if str(service_root) not in sys.path:
    sys.path.insert(0, str(service_root))

from celery_app import celery_app
from tts_engine import tts_engine_manager
from database import init_db

logger = get_task_logger(__name__)

# Initialize DB and Engine on module load (or lazily in task)
# For Celery, lazy initialization inside task or worker_process_init signal is often safer.

@celery_app.task(name="f5_tts.tasks.generate_tts", bind=True)
def generate_tts_task(self, text: str, voice: str, user_id: int, platform: str, channel: str, message_id: str):
    """
    Celery task for TTS generation.
    Wraps the async generation logic within a sync task (using asyncio.run).
    """
    logger.info(f"Processing TTS task {self.request.id}: {text[:50]}...")
    
    try:
        # We need to run async code in this sync task
        # Ideally, we'd use celery[asyncio] but standard celery is synchronous.
        # So we wrap it.
        result = asyncio.run(_process_tts_async(text, voice, user_id, platform, channel, message_id))
        return result
    except Exception as e:
        logger.exception("TTS Task failed")
        # Retry logic could be added here
        raise self.retry(exc=e, countdown=5, max_retries=3)

async def _process_tts_async(text: str, voice: str, user_id: int, platform: str, channel: str, message_id: str):
    """
    Async implementation of TTS generation logic.
    """
    # Ensure DB and Engine are initialized
    init_db()
    await tts_engine_manager.initialize()
    
    # Imports inside function to avoid circular deps or early init
    from async_tts_engine import async_tts_engine
    from async_audio_converter import async_audio_converter
    
    # Initialize engines
    if not async_tts_engine.is_initialized:
        await async_tts_engine.initialize()
        
    # Start converter workers if needed (though locally we might just call function)
    if not async_audio_converter._running:
        await async_audio_converter.start_workers()

    # 1. Synthesize
    logger.info(f"Synthesizing: {text[:30]}")
    synthesis_task_id = await async_tts_engine.synthesize_speech_async(text, voice, user_id)
    
    # Poll for synthesis result
    synthesis_result = None
    for _ in range(60): # 30 seconds
        synthesis_result = await async_tts_engine.get_task_result(synthesis_task_id)
        if synthesis_result:
            break
        await asyncio.sleep(0.5)
        
    if not synthesis_result:
        raise Exception("TTS synthesis timed out")

    # 2. Convert
    original_path = Path(synthesis_result)
    converted_path = original_path.parent / f"{original_path.stem}_converted.wav"
    
    conversion_task_id = await async_audio_converter.convert_audio_async(
        str(original_path), 
        str(converted_path), 
        "wav", 
        22050
    )
    
    conversion_result = None
    for _ in range(60):
        conversion_result = await async_audio_converter.get_conversion_result(conversion_task_id)
        if conversion_result:
            break
        await asyncio.sleep(0.5)
        
    final_path = conversion_result if conversion_result else synthesis_result
    
    # Cleanup original if converted
    if final_path != str(original_path) and original_path.exists():
        try:
            original_path.unlink()
        except Exception:
            pass

    # 3. Publish result (or return it and let bot_service handle)
    # The original worker published to Redis Pub/Sub for the bot to pick up.
    # We should replicate this so the bot knows it's done.
    
    import redis
    import json
    import time
    
    redis_client = redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
    
    audio_url = f"{os.getenv('TTS_SERVICE_URL', 'http://localhost:8001')}/audio/{os.path.basename(final_path)}"
    
    result_payload = {
        "type": "tts_synthesized",
        "audio_url": audio_url,
        "text": text,
        "voice": voice,
        "channel": channel,
        "platform": platform,
        "user_id": user_id,
        "message_id": message_id,
        "worker_id": "celery_worker",
        "timestamp": time.time()
    }
    
    channel_key = f"tts_results:{channel}"
    redis_client.publish(channel_key, json.dumps(result_payload))
    logger.info(f"Published result to {channel_key}")
    
    return result_payload




