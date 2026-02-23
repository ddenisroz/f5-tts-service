import asyncio
import logging
import time
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import redis
logger = logging.getLogger(__name__)
from analysis_logging import log_tts_generation, log_error, set_correlation_id, clear_correlation_id

class TaskPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4

@dataclass
class WorkerTask:
    """Задача для обработки воркерами"""
    task_id: str
    text: str
    voice: str
    user_id: Optional[int]
    priority: TaskPriority
    created_at: float
    stream_id: str
    use_gpu: bool = True
    retry_count: int = 0
    max_retries: int = 3

@dataclass
class WorkerStats:
    """Статистика воркера"""
    worker_id: str
    tasks_processed: int = 0
    tasks_failed: int = 0
    avg_processing_time: float = 0.0
    last_activity: float = 0.0
    is_active: bool = False
    current_task: Optional[str] = None

class AsyncWorkerManager:
    """Text cleaned."""

    def __init__(self, redis_url: str='redis://localhost:6379/0', input_stream: str='tts_requests', output_stream: str='tts_results', consumer_group: str='tts_workers', max_workers: int=4, worker_timeout: float=300.0, poll_interval: float=0.1):
        self.redis_url = redis_url
        self.input_stream = input_stream
        self.output_stream = output_stream
        self.consumer_group = consumer_group
        self.max_workers = max_workers
        self.worker_timeout = worker_timeout
        self.poll_interval = poll_interval
        self.redis_client = None
        self.gpu_worker_pool = None
        self.tts_engine_manager = None
        self.workers: Dict[str, asyncio.Task] = {}
        self.worker_stats: Dict[str, WorkerStats] = {}
        self.running = False
        self.priority_queues = {TaskPriority.CRITICAL: asyncio.Queue(), TaskPriority.HIGH: asyncio.Queue(), TaskPriority.NORMAL: asyncio.Queue(), TaskPriority.LOW: asyncio.Queue()}
        self.global_stats = {'total_tasks': 0, 'completed_tasks': 0, 'failed_tasks': 0, 'active_workers': 0, 'queue_sizes': {priority.value: 0 for priority in TaskPriority}, 'avg_processing_time': 0.0, 'last_activity': 0.0}

    async def initialize(self):
        """Text cleaned."""
        try:
            await self._connect_redis()
            await self._initialize_components()
            await self._start_workers()
            await self._start_task_dispatcher()
            self.running = True
            logger.info(f'AsyncWorkerManager initialized with {self.max_workers} workers')
        except Exception:
            logger.exception('Failed to initialize AsyncWorkerManager')
            raise

    async def _connect_redis(self):
        """Подключение к Redis"""
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            await asyncio.get_event_loop().run_in_executor(None, self.redis_client.ping)
            try:
                await asyncio.get_event_loop().run_in_executor(None, self.redis_client.xgroup_create, self.input_stream, self.consumer_group, id='0', mkstream=True)
            except redis.exceptions.ResponseError as e:
                if 'BUSYGROUP' not in str(e):
                    raise
            logger.info(f'Connected to Redis: {self.redis_url}')
        except Exception:
            logger.exception('Failed to connect to Redis')
            raise

    async def _initialize_components(self):
        """Text cleaned."""
        try:
            from tts_engine import tts_engine_manager
            from tts_limits_service import tts_limits_service
            self.tts_engine_manager = tts_engine_manager
            self.tts_limits_service = tts_limits_service
            try:
                from gpu_worker_pool import gpu_worker_pool
                if hasattr(gpu_worker_pool, 'running') and gpu_worker_pool.running:
                    self.gpu_worker_pool = gpu_worker_pool
                    logger.info('GPU Worker Pool available')
                else:
                    logger.info('GPU Worker Pool not available, using CPU only')
            except Exception:
                logger.exception('GPU Worker Pool not available')
        except Exception:
            logger.exception('Failed to initialize components')
            raise

    async def _start_workers(self):
        """Запуск воркеров"""
        for i in range(self.max_workers):
            worker_id = f'worker_{i}'
            task = asyncio.create_task(self._worker_loop(worker_id))
            self.workers[worker_id] = task
            self.worker_stats[worker_id] = WorkerStats(worker_id=worker_id)
        logger.info(f'Started {self.max_workers} workers')

    async def _start_task_dispatcher(self):
        """Запуск диспетчера задач"""
        dispatcher_task = asyncio.create_task(self._task_dispatcher_loop())
        self.workers['dispatcher'] = dispatcher_task
        logger.info('Task dispatcher started')

    async def _task_dispatcher_loop(self):
        """Основной цикл диспетчера задач"""
        logger.info('Task dispatcher loop started')
        while self.running:
            try:
                tasks = await self._get_tasks_from_redis()
                for task in tasks:
                    await self.priority_queues[task.priority].put(task)
                    self.global_stats['total_tasks'] += 1
                    self.global_stats['queue_sizes'][task.priority.value] += 1
                await self._update_queue_stats()
                await asyncio.sleep(self.poll_interval)
            except Exception:
                logger.exception('Error in task dispatcher')
                await asyncio.sleep(1)

    async def _get_tasks_from_redis(self) -> List[WorkerTask]:
        """Получение задач из Redis Stream"""
        try:
            messages = await asyncio.get_event_loop().run_in_executor(None, self._read_redis_stream)
            tasks = []
            for (stream_id, fields) in messages:
                try:
                    task_data = json.loads(fields.get('data', '{}'))
                    priority_value = task_data.get('priority', 2)
                    priority = TaskPriority(priority_value) if priority_value in [1, 2, 3, 4] else TaskPriority.NORMAL
                    use_gpu = await self._should_use_gpu(task_data)
                    task = WorkerTask(task_id=task_data.get('task_id', stream_id), text=task_data.get('text', ''), voice=task_data.get('voice', 'female_1'), user_id=task_data.get('user_id'), priority=priority, created_at=float(task_data.get('created_at', time.time())), stream_id=stream_id, use_gpu=use_gpu)
                    tasks.append(task)
                except Exception:
                    logger.exception('Error parsing task {stream_id}')
                    try:
                        self.redis_client.xack(self.input_stream, self.consumer_group, stream_id)
                    except Exception:
                        pass
            return tasks
        except Exception:
            logger.exception('Error getting tasks from Redis')
            return []

    def _read_redis_stream(self) -> List[Tuple[str, Dict[str, str]]]:
        """Чтение из Redis Stream"""
        try:
            messages = self.redis_client.xreadgroup(self.consumer_group, 'dispatcher', {self.input_stream: '>'}, count=10, block=100)
            return messages[0][1] if messages else []
        except Exception:
            logger.exception('Error reading Redis stream')
            return []

    async def _should_use_gpu(self, task_data: Dict[str, Any]) -> bool:
        """Определение, использовать ли GPU для задачи"""
        try:
            if not self.gpu_worker_pool:
                return False
            gpu_metrics = self.gpu_worker_pool.get_gpu_metrics()
            if gpu_metrics and gpu_metrics.memory_usage_percent > 0.95:
                return False
            priority = task_data.get('priority', 2)
            if priority < 0:
                return False
            text = task_data.get('text', '')
            if len(text) < 50:
                return False
            return True
        except Exception:
            logger.exception('Error checking GPU availability')
            return False

    async def _worker_loop(self, worker_id: str):
        """Основной цикл воркера"""
        logger.info(f'Worker {worker_id} started')
        stats = self.worker_stats[worker_id]
        while self.running:
            try:
                task = await self._get_next_task()
                if task:
                    stats.is_active = True
                    stats.current_task = task.task_id
                    stats.last_activity = time.time()
                    logger.info(f'Worker {worker_id} processing task {task.task_id} (priority: {task.priority.name})')
                    set_correlation_id(task.task_id[:8])
                    start_time = time.time()
                    success = await self._process_task(task, worker_id)
                    processing_time = time.time() - start_time
                    if success:
                        stats.tasks_processed += 1
                        self.global_stats['completed_tasks'] += 1
                        log_tts_generation(text=task.text, voice=task.voice, success=True, user_id=task.user_id, duration_ms=processing_time * 1000)
                        if task.user_id:
                            try:
                                from database import SessionLocal
                                db = SessionLocal()
                                self.tts_limits_service.log_request(user_id=task.user_id, text=task.text, processing_time=processing_time, processing_type='gpu' if task.use_gpu else 'cpu', priority=task.priority.value, success=True, db=db)
                                db.close()
                            except Exception:
                                logger.exception('Error logging user usage')
                    else:
                        stats.tasks_failed += 1
                        self.global_stats['failed_tasks'] += 1
                        log_tts_generation(text=task.text, voice=task.voice, success=False, user_id=task.user_id, duration_ms=processing_time * 1000, error='Processing failed')
                        if task.user_id:
                            try:
                                from database import SessionLocal
                                db = SessionLocal()
                                self.tts_limits_service.log_request(user_id=task.user_id, text=task.text, processing_time=processing_time, processing_type='gpu' if task.use_gpu else 'cpu', priority=task.priority.value, success=False, db=db)
                                db.close()
                            except Exception:
                                logger.exception('Error logging failed user usage')
                    total_tasks = stats.tasks_processed + stats.tasks_failed
                    if total_tasks > 0:
                        stats.avg_processing_time = (stats.avg_processing_time * (total_tasks - 1) + processing_time) / total_tasks
                    stats.is_active = False
                    stats.current_task = None
                    self.global_stats['last_activity'] = time.time()
                    clear_correlation_id()
                else:
                    await asyncio.sleep(self.poll_interval)
            except Exception as e:
                logger.exception('Error in worker {worker_id}')
                log_error(feature='tts_worker', error=e, context=f'worker_{worker_id}')
                stats.is_active = False
                stats.current_task = None
                clear_correlation_id()
                await asyncio.sleep(1)

    async def _get_next_task(self) -> Optional[WorkerTask]:
        """Получение следующей задачи по приоритету"""
        for priority in [TaskPriority.CRITICAL, TaskPriority.HIGH, TaskPriority.NORMAL, TaskPriority.LOW]:
            try:
                task = self.priority_queues[priority].get_nowait()
                self.global_stats['queue_sizes'][priority.value] -= 1
                return task
            except asyncio.QueueEmpty:
                continue
        return None

    async def _process_task(self, task: WorkerTask, worker_id: str) -> bool:
        """Обработка TTS задачи"""
        try:
            if task.use_gpu and self.gpu_worker_pool:
                result_path = await self._process_gpu_task(task)
            else:
                result_path = await self._process_cpu_task(task)
            if result_path:
                await self._send_result(task, result_path, None)
                self.redis_client.xack(self.input_stream, self.consumer_group, task.stream_id)
                logger.info(f'Task {task.task_id} completed successfully by {worker_id}')
                return True
            else:
                await self._handle_task_error(task, 'Processing failed')
                return False
        except Exception as e:
            logger.exception('Error processing task {task.task_id}')
            await self._handle_task_error(task, str(e))
            return False

    async def _process_gpu_task(self, task: WorkerTask) -> Optional[str]:
        """Обработка задачи на GPU"""
        try:
            gpu_task_id = await self.gpu_worker_pool.submit_task(text=task.text, voice=task.voice, user_id=task.user_id, priority=task.priority.value)
            max_wait_time = self.worker_timeout
            wait_time = 0
            while wait_time < max_wait_time:
                result = await self.gpu_worker_pool.get_task_result(gpu_task_id)
                if result:
                    return result.get('result_path')
                await asyncio.sleep(0.5)
                wait_time += 0.5
            logger.error(f'GPU task {gpu_task_id} timed out')
            return None
        except Exception:
            logger.exception('Error processing GPU task')
            return None

    async def _process_cpu_task(self, task: WorkerTask) -> Optional[str]:
        """Обработка задачи на CPU"""
        try:
            if not self.tts_engine_manager or not self.tts_engine_manager.is_ready():
                logger.error('TTS engine not ready')
                return None
            result_path = await self.tts_engine_manager.synthesize_speech_async(text=task.text, voice=task.voice, user_id=task.user_id)
            return result_path
        except Exception:
            logger.exception('Error processing CPU task')
            return None

    async def _send_result(self, task: WorkerTask, result_path: str, error: Optional[str]):
        """Отправка результата в Redis"""
        try:
            result_data = {'task_id': task.task_id, 'status': 'completed' if result_path else 'failed', 'result_path': result_path or '', 'error': error or '', 'processing_time': time.time() - task.created_at, 'completed_at': time.time(), 'worker_id': 'gpu' if task.use_gpu else 'cpu'}
            self.redis_client.xadd(self.output_stream, result_data)
        except Exception:
            logger.exception('Error sending result')

    async def _handle_task_error(self, task: WorkerTask, error: str):
        """Обработка ошибки задачи"""
        try:
            task.retry_count += 1
            if task.retry_count < task.max_retries:
                logger.info(f'Retrying task {task.task_id} (attempt {task.retry_count})')
                await asyncio.sleep(1)
                await self.priority_queues[task.priority].put(task)
            else:
                logger.exception('Task {task.task_id} failed after {task.max_retries} attempts')
                await self._send_result(task, None, error)
                self.redis_client.xack(self.input_stream, self.consumer_group, task.stream_id)
        except Exception:
            logger.exception('Error handling task error')

    async def _update_queue_stats(self):
        """Обновление статистики очередей"""
        for priority in TaskPriority:
            self.global_stats['queue_sizes'][priority.value] = self.priority_queues[priority].qsize()

    async def stop(self):
        """Остановка менеджера воркеров"""
        logger.info('Stopping AsyncWorkerManager...')
        self.running = False
        for (worker_id, task) in self.workers.items():
            task.cancel()
        if self.workers:
            await asyncio.gather(*self.workers.values(), return_exceptions=True)
        self.workers.clear()
        self.worker_stats.clear()
        if self.redis_client:
            self.redis_client.close()
        logger.info('AsyncWorkerManager stopped')

    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики"""
        active_workers = sum((1 for stats in self.worker_stats.values() if stats.is_active))
        self.global_stats['active_workers'] = active_workers
        return {**self.global_stats, 'workers': {worker_id: {'tasks_processed': stats.tasks_processed, 'tasks_failed': stats.tasks_failed, 'avg_processing_time': stats.avg_processing_time, 'is_active': stats.is_active, 'current_task': stats.current_task, 'last_activity': stats.last_activity} for (worker_id, stats) in self.worker_stats.items()}, 'queue_sizes': self.global_stats['queue_sizes'], 'running': self.running}

    def get_queue_sizes(self) -> Dict[str, int]:
        """Получение размеров очередей"""
        return {priority.name: self.priority_queues[priority].qsize() for priority in TaskPriority}
async_worker_manager = AsyncWorkerManager()
