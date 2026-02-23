import asyncio
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from TTS_rus_engine.russian_tts import RussianTTS
logger = logging.getLogger(__name__)

@dataclass
class SynthesisTask:
    """Задача синтеза речи"""
    task_id: str
    text: str
    voice: str
    user_id: int
    channel: str
    platform: str
    priority: int
    created_at: float
    status: str = 'pending'
    result: Optional[str] = None
    error: Optional[str] = None

class AsyncTTSEngine:
    """
    Асинхронный TTS движок с параллельным синтезом
    """

    def __init__(self, max_concurrent_synthesis: int=4):
        self.max_concurrent_synthesis = max_concurrent_synthesis
        self.semaphore = asyncio.Semaphore(max_concurrent_synthesis)
        self.tts_engine = None
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent_synthesis)
        self.is_initialized = False
        self.stats = {'total_tasks': 0, 'completed_tasks': 0, 'failed_tasks': 0, 'active_tasks': 0, 'queue_size': 0, 'avg_processing_time': 0.0}
        self.task_queue = asyncio.Queue()
        self.active_tasks: Dict[str, SynthesisTask] = {}
        self.completed_tasks: Dict[str, SynthesisTask] = {}
        self._worker_tasks = []
        self._running = False

    async def initialize(self):
        """Text cleaned."""
        try:
            logger.info(f'Initializing Async TTS Engine with {self.max_concurrent_synthesis} workers...')
            loop = asyncio.get_event_loop()
            self.tts_engine = await loop.run_in_executor(self.executor, self._init_tts_engine)
            self.is_initialized = True
            logger.info('Async TTS Engine initialized successfully')
            await self.start_workers()
        except Exception:
            logger.exception('Failed to initialize Async TTS Engine')
            raise

    def _init_tts_engine(self) -> RussianTTS:
        """Text cleaned."""
        try:
            engine = RussianTTS()
            logger.info('TTS engine initialized in background thread')
            return engine
        except Exception:
            logger.exception('Failed to initialize TTS engine')
            raise

    async def start_workers(self):
        """Запуск worker'ов для обработки задач"""
        if self._running:
            return
        self._running = True
        for i in range(self.max_concurrent_synthesis):
            task = asyncio.create_task(self._worker(f'worker_{i}'))
            self._worker_tasks.append(task)
        logger.info(f'Started {self.max_concurrent_synthesis} TTS workers')

    async def stop_workers(self):
        """Остановка worker'ов"""
        if not self._running:
            return
        self._running = False
        for task in self._worker_tasks:
            task.cancel()
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()
        self.executor.shutdown(wait=True)
        logger.info('TTS workers stopped')

    async def _worker(self, worker_name: str):
        """Worker для обработки TTS задач"""
        logger.info(f'TTS worker {worker_name} started')
        while self._running:
            try:
                task = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)
                await self._process_task(task, worker_name)
            except asyncio.TimeoutError:
                continue
            except Exception:
                logger.exception('Worker {worker_name} error')
                await asyncio.sleep(1)
        logger.info(f'TTS worker {worker_name} stopped')

    async def _process_task(self, task: SynthesisTask, worker_name: str):
        """Обработка TTS задачи"""
        try:
            task.status = 'processing'
            self.active_tasks[task.task_id] = task
            self.stats['active_tasks'] = len(self.active_tasks)
            logger.info(f'Worker {worker_name} processing task {task.task_id}: {task.text[:50]}...')
            start_time = time.time()
            loop = asyncio.get_event_loop()
            audio_path = await loop.run_in_executor(self.executor, self._synthesize_speech_sync, task.text, task.voice)
            processing_time = time.time() - start_time
            if audio_path and Path(audio_path).exists():
                task.result = audio_path
                task.status = 'completed'
                self.stats['completed_tasks'] += 1
                logger.info(f'Worker {worker_name} completed task {task.task_id} in {processing_time:.2f}s')
            else:
                task.status = 'failed'
                task.error = 'TTS synthesis failed'
                self.stats['failed_tasks'] += 1
                logger.error(f'Worker {worker_name} failed task {task.task_id}')
            self._update_stats(processing_time)
            self.completed_tasks[task.task_id] = task
            if task.task_id in self.active_tasks:
                del self.active_tasks[task.task_id]
            self.stats['active_tasks'] = len(self.active_tasks)
        except Exception as e:
            logger.exception('Worker {worker_name} error processing task {task.task_id}')
            task.status = 'failed'
            task.error = str(e)
            self.stats['failed_tasks'] += 1

    def _synthesize_speech_sync(self, text: str, voice: str) -> Optional[str]:
        """Синхронный синтез речи в отдельном потоке"""
        try:
            if not self.tts_engine:
                logger.error('TTS engine not initialized')
                return None
            return self.tts_engine.synthesize(text, voice)
        except Exception:
            logger.exception('Sync synthesis error')
            return None

    def _update_stats(self, processing_time: float):
        """Обновление статистики"""
        self.stats['total_tasks'] += 1
        total_completed = self.stats['completed_tasks'] + self.stats['failed_tasks']
        if total_completed > 0:
            current_avg = self.stats['avg_processing_time']
            self.stats['avg_processing_time'] = (current_avg * (total_completed - 1) + processing_time) / total_completed

    async def synthesize_speech_async(self, text: str, voice: str='female_1', user_id: int=None, channel: str=None, platform: str='twitch', priority: int=1) -> str:
        """
        Асинхронный синтез речи с добавлением в очередь
        
        Returns:
            task_id: ID задачи для отслеживания
        """
        if not self.is_initialized:
            raise RuntimeError('Async TTS Engine not initialized')
        task_id = f'task_{int(time.time() * 1000)}_{user_id or 0}'
        task = SynthesisTask(task_id=task_id, text=text, voice=voice, user_id=user_id or 0, channel=channel or f'user_{user_id}', platform=platform, priority=priority, created_at=time.time())
        await self.task_queue.put(task)
        self.stats['queue_size'] = self.task_queue.qsize()
        logger.info(f'TTS task {task_id} queued for synthesis')
        return task_id

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Получить статус задачи"""
        if task_id in self.active_tasks:
            task = self.active_tasks[task_id]
        elif task_id in self.completed_tasks:
            task = self.completed_tasks[task_id]
        else:
            return None
        return {'task_id': task.task_id, 'status': task.status, 'text': task.text[:100] + '...' if len(task.text) > 100 else task.text, 'voice': task.voice, 'user_id': task.user_id, 'channel': task.channel, 'platform': task.platform, 'priority': task.priority, 'created_at': task.created_at, 'result': task.result, 'error': task.error}

    async def get_task_result(self, task_id: str) -> Optional[str]:
        """Получить результат задачи"""
        if task_id in self.completed_tasks:
            task = self.completed_tasks[task_id]
            if task.status == 'completed':
                return task.result
        return None

    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику движка"""
        return {**self.stats, 'queue_size': self.task_queue.qsize(), 'is_initialized': self.is_initialized, 'is_running': self._running, 'max_concurrent_synthesis': self.max_concurrent_synthesis}

    async def cleanup_old_tasks(self, max_age_hours: int=24):
        """Очистка старых задач"""
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        tasks_to_remove = []
        for (task_id, task) in self.completed_tasks.items():
            if current_time - task.created_at > max_age_seconds:
                tasks_to_remove.append(task_id)
        for task_id in tasks_to_remove:
            task = self.completed_tasks.pop(task_id)
            if task.result and Path(task.result).exists():
                try:
                    Path(task.result).unlink()
                    logger.info(f'Cleaned up old task file: {task.result}')
                except Exception:
                    logger.exception('Error cleaning up task file {task.result}')
        if tasks_to_remove:
            logger.info(f'Cleaned up {len(tasks_to_remove)} old tasks')
async_tts_engine = AsyncTTSEngine()
