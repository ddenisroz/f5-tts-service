#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TTS Worker для обработки очередей Redis Streams
Обрабатывает TTS задачи асинхронно и публикует результаты через Redis Pub/Sub
"""

import os
import sys
import asyncio
import logging
import signal
import time
import json
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Загружае переенные окружения
load_dotenv()

# Настройка путей
service_root = Path(__file__).resolve().parent
if str(service_root) not in sys.path:
    sys.path.insert(0, str(service_root))

# порты TTS сервиса
from tts_engine import tts_engine_manager
from database import init_db

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TTSWorker:
    """
    TTS Worker для обработки задач из Redis Streams
    """
    
    def __init__(self, worker_id: str = None):
        self.worker_id = worker_id or os.getenv('WORKER_ID', f'worker_{os.getpid()}')
        self.redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        self.redis_client = None
        self.stream_name = "tts_requests"
        self.consumer_group = "tts_workers"
        self.running = False
        self.processed_tasks = 0
        self.failed_tasks = 0
        self.start_time = time.time()
        
        # Статистика
        self.stats = {
            'processed': 0,
            'failed': 0,
            'start_time': self.start_time,
            'last_activity': None
        }
    
    async def connect(self):
        """Подключение к Redis"""
        try:
            import redis
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            
            # Тестируе соединение
            await asyncio.get_event_loop().run_in_executor(None, self.redis_client.ping)
            logger.info(f"Worker {self.worker_id} connected to Redis successfully")
            
            # Создае consumer group если не существует
            await self._ensure_consumer_group()
            
        except Exception:
            logger.exception("Worker {self.worker_id} failed to connect to Redis")
            raise
    
    async def _ensure_consumer_group(self):
        """Создает consumer group если не существует"""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.redis_client.xgroup_create,
                self.stream_name,
                self.consumer_group,
                '0',
                mkstream=True
            )
            logger.info(f"Worker {self.worker_id} created consumer group {self.consumer_group}")
        except Exception as e:
            if "BUSYGROUP" in str(e):
                logger.info(f"Worker {self.worker_id} consumer group already exists")
            else:
                logger.exception("Worker {self.worker_id} error creating consumer group")
                raise
    
    async def start(self):
        """Запуск worker'а"""
        if self.running:
            logger.warning(f"Worker {self.worker_id} is already running")
            return
        
        try:
            await self.connect()
            await self._initialize_tts_engine()
            
            self.running = True
            logger.info(f"TTS Worker {self.worker_id} started successfully")
            
            # Основной цикл обработки
            await self._process_loop()
            
        except Exception:
            logger.exception("Worker {self.worker_id} failed to start")
            raise
        finally:
            await self.stop()
    
    async def stop(self):
        """Остановка worker'а"""
        if not self.running:
            return
        
        self.running = False
        logger.info(f"TTS Worker {self.worker_id} stopping...")
        
        if self.redis_client:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    self.redis_client.close
                )
            except Exception:
                logger.exception("Error closing Redis connection")
        
        logger.info(f"TTS Worker {self.worker_id} stopped. Processed: {self.processed_tasks}, Failed: {self.failed_tasks}")
    
    async def _initialize_tts_engine(self):
        """нициализация TTS движка"""
        try:
            # нициализируе базу данных
            init_db()
            
            # нициализируе TTS движок
            await tts_engine_manager.initialize()
            
            logger.info(f"Worker {self.worker_id} TTS engine initialized successfully")
            
        except Exception:
            logger.exception("Worker {self.worker_id} failed to initialize TTS engine")
            raise
    
    async def _process_loop(self):
        """Основной цикл обработки задач"""
        while self.running:
            try:
                # Получае задачи из очереди
                tasks = await self._get_tasks()
                
                if tasks:
                    for task in tasks:
                        await self._process_task(task)
                else:
                    # Если нет задач, жде неного
                    await asyncio.sleep(0.1)
                    
            except Exception:
                logger.exception("Worker {self.worker_id} error in process loop")
                await asyncio.sleep(1)
    
    async def _get_tasks(self) -> list:
        """Получить задачи из Redis Stream"""
        try:
            messages = await asyncio.get_event_loop().run_in_executor(
                None,
                self.redis_client.xreadgroup,
                self.consumer_group,
                self.worker_id,
                {self.stream_name: '>'},
                count=1,
                block=1000  # 1 секунда блокировки
            )
            
            tasks = []
            for stream, msgs in messages:
                for msg_id, fields in msgs:
                    tasks.append({
                        'message_id': msg_id,
                        'fields': fields
                    })
            
            return tasks
            
        except Exception as e:
            if "NOGROUP" in str(e):
                # Группа не существует, создае
                await self._ensure_consumer_group()
                return []
            else:
                logger.exception("Worker {self.worker_id} error reading tasks")
                return []
    
    async def _process_task(self, task: Dict[str, Any]):
        """Обработка TTS задачи"""
        message_id = task['message_id']
        fields = task['fields']
        
        try:
            # звлекае данные задачи
            user_id = int(fields.get('user_id', 0))
            text = fields.get('text', '')
            voice = fields.get('voice', 'female_1')
            channel = fields.get('channel', '')
            platform = fields.get('platform', 'twitch')
            priority = int(fields.get('priority', 1))
            
            logger.info(f"Worker {self.worker_id} processing task {message_id}: {text[:50]}...")
            
            # Проверяе, не пустой ли текст
            if not text or not text.strip():
                logger.warning(f"Worker {self.worker_id} skipping empty text task {message_id}")
                await self._acknowledge_task(message_id)
                return
            
            # Генерируе TTS
            audio_url = await self._synthesize_speech(text, voice, user_id)
            
            if audio_url:
                # Публикуе результат через Redis Pub/Sub
                result = {
                    "type": "tts_synthesized",
                    "audio_url": audio_url,
                    "text": text,
                    "voice": voice,
                    "channel": channel,
                    "platform": platform,
                    "user_id": user_id,
                    "message_id": message_id,
                    "worker_id": self.worker_id,
                    "timestamp": time.time()
                }
                
                await self._publish_result(channel, result)
                
                # Подтверждае обработку задачи
                await self._acknowledge_task(message_id)
                
                self.processed_tasks += 1
                self.stats['processed'] = self.processed_tasks
                self.stats['last_activity'] = time.time()
                
                logger.info(f"Worker {self.worker_id} completed task {message_id} successfully")
            else:
                logger.error(f"Worker {self.worker_id} TTS generation failed for task {message_id}")
                self.failed_tasks += 1
                self.stats['failed'] = self.failed_tasks
                
        except Exception:
            logger.exception("Worker {self.worker_id} error processing task {message_id}")
            self.failed_tasks += 1
            self.stats['failed'] = self.failed_tasks
    
    async def _synthesize_speech(self, text: str, voice: str, user_id: int) -> Optional[str]:
        """Синтез речи с асинхронной конвертацией"""
        try:
            # спользуе асинхронный TTS движок с конвертацией
            from async_tts_engine import async_tts_engine
            from async_audio_converter import async_audio_converter
            
            # нициализируе асинхронные копоненты если нужно
            if not async_tts_engine.is_initialized:
                await async_tts_engine.initialize()
            
            if not async_audio_converter._running:
                await async_audio_converter.start_workers()
            
            # Синтезируе речь
            synthesis_task_id = await async_tts_engine.synthesize_speech_async(
                text=text,
                voice=voice,
                user_id=user_id
            )
            
            # Жде завершения синтеза
            synthesis_result = None
            max_wait_time = 30  # 30 секунд аксиу
            wait_time = 0
            
            while wait_time < max_wait_time:
                synthesis_result = await async_tts_engine.get_task_result(synthesis_task_id)
                if synthesis_result:
                    break
                await asyncio.sleep(0.5)
                wait_time += 0.5
            
            if not synthesis_result:
                logger.error("TTS synthesis task did not complete in time")
                return None
            
            # Конвертируе в WAV для лучшего качества
            original_path = Path(synthesis_result)
            converted_path = original_path.parent / f"{original_path.stem}_converted.wav"
            
            conversion_task_id = await async_audio_converter.convert_audio_async(
                input_path=str(original_path),
                output_path=str(converted_path),
                target_format="wav",
                target_sample_rate=22050
            )
            
            # Жде завершения конвертации
            conversion_result = None
            wait_time = 0
            
            while wait_time < max_wait_time:
                conversion_result = await async_audio_converter.get_conversion_result(conversion_task_id)
                if conversion_result:
                    break
                await asyncio.sleep(0.5)
                wait_time += 0.5
            
            if not conversion_result:
                logger.warning("Audio conversion did not complete, using original file")
                conversion_result = synthesis_result
            
            # Удаляе оригинальный файл после успешной конвертации
            try:
                if original_path.exists() and conversion_result != synthesis_result:
                    original_path.unlink()
                    logger.info(f"Removed original file after conversion: {original_path}")
            except Exception:
                logger.exception("Failed to remove original file")
            
            if conversion_result and os.path.exists(conversion_result):
                # Форируе URL для аудио файла
                audio_url = f"{os.getenv('TTS_SERVICE_URL', 'http://localhost:8001')}/audio/{os.path.basename(conversion_result)}"
                return audio_url
            else:
                logger.error("TTS synthesis failed: no audio file generated")
                return None
                
        except Exception:
            logger.exception("TTS synthesis error")
            return None
    
    async def _publish_result(self, channel: str, result: Dict[str, Any]):
        """Публикация результата через Redis Pub/Sub"""
        try:
            channel_key = f"tts_results:{channel}"
            message = json.dumps(result)
            
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.redis_client.publish,
                channel_key,
                message
            )
            
            logger.debug(f"Worker {self.worker_id} published result to {channel_key}")
            
        except Exception:
            logger.exception("Worker {self.worker_id} failed to publish result")
    
    async def _acknowledge_task(self, message_id: str):
        """Подтверждение обработки задачи"""
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                self.redis_client.xack,
                self.stream_name,
                self.consumer_group,
                message_id
            )
            
            logger.debug(f"Worker {self.worker_id} acknowledged task {message_id}: {result}")
            
        except Exception:
            logger.exception("Worker {self.worker_id} failed to acknowledge task {message_id}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику worker'а"""
        uptime = time.time() - self.start_time
        return {
            **self.stats,
            'worker_id': self.worker_id,
            'uptime': uptime,
            'running': self.running,
            'processed_per_hour': self.processed_tasks / (uptime / 3600) if uptime > 0 else 0
        }

async def main():
    """Главная функция worker'а"""
    worker_id = os.getenv('WORKER_ID', f'worker_{os.getpid()}')
    worker = TTSWorker(worker_id)
    
    # Обработка сигналов для graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Worker {worker_id} received signal {signum}, shutting down...")
        asyncio.create_task(worker.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info(f"Worker {worker_id} interrupted by user")
    except Exception:
        logger.exception("Worker {worker_id} failed")
        sys.exit(1)
    finally:
        await worker.stop()

if __name__ == "__main__":
    asyncio.run(main())



