import asyncio
import logging
import time
import torch
from typing import Dict, Optional, Any, List
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import json
import redis
logger = logging.getLogger(__name__)

class GPUStatus(Enum):
    IDLE = 'idle'
    LOW_LOAD = 'low_load'
    MEDIUM_LOAD = 'medium_load'
    HIGH_LOAD = 'high_load'
    CRITICAL = 'critical'

@dataclass
class GPUMetrics:
    memory_allocated: int
    memory_reserved: int
    memory_total: int
    memory_usage_percent: float
    gpu_utilization: float
    temperature: Optional[float] = None
    power_usage: Optional[float] = None
    timestamp: float = 0.0

@dataclass
class SynthesisTask:
    task_id: str
    text: str
    voice: str
    user_id: Optional[int]
    priority: int = 0
    created_at: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result_path: Optional[str] = None
    error: Optional[str] = None

class GPUWorkerPool:
    """
    Пул GPU воркеров с динамическим управлением concurrency
    и мониторингом GPU ресурсов
    """

    def __init__(self, config: Optional[Any]=None, redis_url: str='redis://localhost:6379/0', stream_name: str='gpu_tts_requests', consumer_group: str='gpu_workers', min_concurrent: int=1, max_concurrent: int=4, initial_concurrent: int=2, gpu_memory_threshold_low: float=0.3, gpu_memory_threshold_high: float=0.8, gpu_memory_threshold_critical: float=0.9, monitoring_interval: float=5.0, task_timeout: float=300.0):
        if config:
            self.redis_url = config.redis_url
            self.stream_name = config.gpu_stream
            self.consumer_group = config.consumer_group
            self.min_concurrent = config.min_concurrent
            self.max_concurrent = config.max_concurrent
            self.current_concurrent = config.initial_concurrent
            self.gpu_memory_threshold_low = config.gpu_memory_threshold_low
            self.gpu_memory_threshold_high = config.gpu_memory_threshold_high
            self.gpu_memory_threshold_critical = config.gpu_memory_threshold_critical
            self.monitoring_interval = config.monitoring_interval
            self.task_timeout = config.task_timeout
        else:
            self.redis_url = redis_url
            self.stream_name = stream_name
            self.consumer_group = consumer_group
            self.min_concurrent = min_concurrent
            self.max_concurrent = max_concurrent
            self.current_concurrent = initial_concurrent
            self.gpu_memory_threshold_low = gpu_memory_threshold_low
            self.gpu_memory_threshold_high = gpu_memory_threshold_high
            self.gpu_memory_threshold_critical = gpu_memory_threshold_critical
            self.monitoring_interval = monitoring_interval
            self.task_timeout = task_timeout
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.redis_client = None
        self.tts_model = None
        self.semaphore = asyncio.Semaphore(self.current_concurrent)
        self.worker_tasks: List[asyncio.Task] = []
        self.running = False
        self.stats = {'total_tasks': 0, 'completed_tasks': 0, 'failed_tasks': 0, 'active_tasks': 0, 'gpu_memory_usage': 0.0, 'current_concurrent': self.current_concurrent, 'avg_processing_time': 0.0, 'last_gpu_status': GPUStatus.IDLE}
        self.active_tasks: Dict[str, SynthesisTask] = {}
        self.completed_tasks: Dict[str, SynthesisTask] = {}
        self._monitoring_task = None
        self._last_gpu_metrics = None
        logger.info(f'GPUWorkerPool initialized: device={self.device}, concurrent={self.current_concurrent}')

    async def initialize(self):
        """Text cleaned."""
        try:
            await self._connect_redis()
            await self._initialize_tts_model()
            await self._start_gpu_monitoring()
            await self._start_workers()
            self.running = True
            logger.info('GPUWorkerPool initialized successfully')
        except Exception:
            logger.exception('Failed to initialize GPUWorkerPool')
            raise

    async def _connect_redis(self):
        """Подключение к Redis"""
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            await asyncio.get_event_loop().run_in_executor(None, self.redis_client.ping)
            try:
                await asyncio.get_event_loop().run_in_executor(None, self.redis_client.xgroup_create, self.stream_name, self.consumer_group, id='0', mkstream=True)
            except redis.exceptions.ResponseError as e:
                if 'BUSYGROUP' not in str(e):
                    raise
            logger.info(f'Connected to Redis: {self.redis_url}')
        except Exception:
            logger.exception('Failed to connect to Redis')
            raise

    async def _initialize_tts_model(self):
        """Text cleaned."""
        try:
            loop = asyncio.get_event_loop()
            self.tts_model = await loop.run_in_executor(None, self._load_tts_model)
            logger.info('TTS model loaded successfully')
        except Exception:
            logger.exception('Failed to initialize TTS model')
            raise

    def _load_tts_model(self):
        """Загрузка TTS модели в отдельном потоке"""
        from TTS_rus_engine.russian_tts import RussianTTS
        return RussianTTS()

    async def _start_gpu_monitoring(self):
        """Запуск мониторинга GPU"""
        if self.device == 'cpu':
            logger.info('GPU monitoring disabled (CPU mode)')
            return
        self._monitoring_task = asyncio.create_task(self._monitor_gpu())
        logger.info('GPU monitoring started')

    async def _monitor_gpu(self):
        """Мониторинг GPU ресурсов"""
        while self.running:
            try:
                metrics = await self._get_gpu_metrics()
                self._last_gpu_metrics = metrics
                self.stats['gpu_memory_usage'] = metrics.memory_usage_percent
                self.stats['last_gpu_status'] = self._classify_gpu_status(metrics)
                await self._adapt_concurrency(metrics)
                if metrics.memory_usage_percent > 0.5:
                    logger.debug(f"GPU Status: {self.stats['last_gpu_status'].value}, Memory: {metrics.memory_usage_percent:.1%}, Concurrent: {self.current_concurrent}")
                await asyncio.sleep(self.monitoring_interval)
            except Exception:
                logger.exception('Error in GPU monitoring')
                await asyncio.sleep(self.monitoring_interval)

    async def _get_gpu_metrics(self) -> GPUMetrics:
        """Получение метрик GPU"""
        try:
            if self.device == 'cpu':
                return GPUMetrics(memory_allocated=0, memory_reserved=0, memory_total=0, memory_usage_percent=0.0, gpu_utilization=0.0, timestamp=time.time())
            memory_allocated = torch.cuda.memory_allocated()
            memory_reserved = torch.cuda.memory_reserved()
            memory_total = torch.cuda.get_device_properties(0).total_memory
            memory_usage_percent = memory_allocated / memory_total
            try:
                import pynvml
                pynvml.nvmlInit()
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                gpu_utilization = util.gpu / 100.0
                try:
                    temperature = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                except Exception:
                    temperature = None
                try:
                    power_usage = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
                except Exception:
                    power_usage = None
            except ImportError:
                gpu_utilization = 0.0
                temperature = None
                power_usage = None
            return GPUMetrics(memory_allocated=memory_allocated, memory_reserved=memory_reserved, memory_total=memory_total, memory_usage_percent=memory_usage_percent, gpu_utilization=gpu_utilization, temperature=temperature, power_usage=power_usage, timestamp=time.time())
        except Exception:
            logger.exception('Error getting GPU metrics')
            return GPUMetrics(memory_allocated=0, memory_reserved=0, memory_total=0, memory_usage_percent=0.0, gpu_utilization=0.0, timestamp=time.time())

    def _classify_gpu_status(self, metrics: GPUMetrics) -> GPUStatus:
        """Классификация статуса GPU на основе метрик"""
        if metrics.memory_usage_percent >= self.gpu_memory_threshold_critical:
            return GPUStatus.CRITICAL
        elif metrics.memory_usage_percent >= self.gpu_memory_threshold_high:
            return GPUStatus.HIGH_LOAD
        elif metrics.memory_usage_percent >= self.gpu_memory_threshold_low:
            return GPUStatus.MEDIUM_LOAD
        else:
            return GPUStatus.LOW_LOAD

    async def _adapt_concurrency(self, metrics: GPUMetrics):
        """Адаптация количества одновременных задач на основе GPU метрик"""
        old_concurrent = self.current_concurrent
        if metrics.memory_usage_percent >= self.gpu_memory_threshold_critical:
            self.current_concurrent = self.min_concurrent
        elif metrics.memory_usage_percent >= self.gpu_memory_threshold_high:
            self.current_concurrent = max(self.min_concurrent, self.current_concurrent - 1)
        elif metrics.memory_usage_percent <= self.gpu_memory_threshold_low:
            self.current_concurrent = min(self.max_concurrent, self.current_concurrent + 1)
        if self.current_concurrent != old_concurrent:
            await self._update_semaphore()
            self.stats['current_concurrent'] = self.current_concurrent
            logger.info(f'Adjusted concurrency: {old_concurrent} -> {self.current_concurrent} (GPU memory: {metrics.memory_usage_percent:.1%})')

    async def _update_semaphore(self):
        """Обновление семафора с новым количеством воркеров"""
        old_semaphore = self.semaphore
        self.semaphore = asyncio.Semaphore(self.current_concurrent)
        while old_semaphore._value < old_semaphore._initial_value:
            await asyncio.sleep(0.1)

    async def _start_workers(self):
        """Запуск воркеров для обработки задач"""
        for i in range(self.current_concurrent):
            task = asyncio.create_task(self._worker(f'gpu_worker_{i}'))
            self.worker_tasks.append(task)
        logger.info(f'Started {self.current_concurrent} GPU workers')

    async def _worker(self, worker_name: str):
        """Воркер для обработки TTS задач"""
        logger.info(f'GPU worker {worker_name} started')
        while self.running:
            try:
                messages = await asyncio.get_event_loop().run_in_executor(None, self._get_next_task, worker_name)
                if not messages:
                    await asyncio.sleep(1)
                    continue
                for (stream_id, fields) in messages:
                    await self._process_task(stream_id, fields, worker_name)
            except Exception:
                logger.exception('Error in GPU worker {worker_name}')
                await asyncio.sleep(5)

    def _get_next_task(self, worker_name: str):
        """Получение следующей задачи из Redis Stream"""
        try:
            messages = self.redis_client.xreadgroup(self.consumer_group, worker_name, {self.stream_name: '>'}, count=1, block=1000)
            return messages[0][1] if messages else []
        except Exception:
            logger.exception('Error reading from Redis stream')
            return []

    async def _process_task(self, stream_id: str, fields: Dict[str, str], worker_name: str):
        """Обработка TTS задачи"""
        try:
            task_data = json.loads(fields.get('data', '{}'))
            task = SynthesisTask(task_id=task_data.get('task_id', stream_id), text=task_data.get('text', ''), voice=task_data.get('voice', 'female_1'), user_id=task_data.get('user_id'), priority=task_data.get('priority', 0), created_at=float(task_data.get('created_at', time.time())), started_at=time.time())
            logger.info(f'Processing task {task.task_id} in {worker_name}')
            async with self.semaphore:
                result_path = await self._synthesize_speech(task)
                if result_path:
                    task.completed_at = time.time()
                    task.result_path = result_path
                    self.completed_tasks[task.task_id] = task
                    self.stats['completed_tasks'] += 1
                    await self._send_result(task)
                    logger.info(f'Task {task.task_id} completed successfully')
                else:
                    task.error = 'Synthesis failed'
                    task.completed_at = time.time()
                    self.completed_tasks[task.task_id] = task
                    self.stats['failed_tasks'] += 1
                    logger.error(f'Task {task.task_id} failed')
                self.redis_client.xack(self.stream_name, self.consumer_group, stream_id)
        except Exception:
            logger.exception('Error processing task {stream_id}')
            try:
                self.redis_client.xack(self.stream_name, self.consumer_group, stream_id)
            except Exception:
                pass

    async def _synthesize_speech(self, task: SynthesisTask) -> Optional[str]:
        """Синтез речи с использованием GPU"""
        try:
            loop = asyncio.get_event_loop()
            result_path = await loop.run_in_executor(None, self._do_tts_synthesis, task.text, task.voice)
            return result_path
        except Exception:
            logger.exception('Error in speech synthesis')
            return None

    def _do_tts_synthesis(self, text: str, voice: str) -> Optional[str]:
        """Синтез речи в отдельном потоке"""
        try:
            if not self.tts_model:
                logger.error('TTS model not initialized')
                return None
            result_path = self.tts_model.synthesize(text, voice)
            if result_path and Path(result_path).exists():
                return result_path
            else:
                logger.error('TTS synthesis failed: no output file')
                return None
        except Exception:
            logger.exception('TTS synthesis error')
            return None

    async def _send_result(self, task: SynthesisTask):
        """Отправка результата обратно в Redis"""
        try:
            result_data = {'task_id': task.task_id, 'status': 'completed' if task.result_path else 'failed', 'result_path': task.result_path or '', 'error': task.error or '', 'processing_time': task.completed_at - task.started_at if task.completed_at and task.started_at else 0, 'completed_at': task.completed_at or time.time()}
            self.redis_client.xadd(f'{self.stream_name}_results', result_data)
        except Exception:
            logger.exception('Error sending result')

    async def submit_task(self, text: str, voice: str, user_id: Optional[int]=None, priority: int=0) -> str:
        """Отправка задачи в очередь"""
        try:
            task_id = f"task_{int(time.time() * 1000)}_{user_id or 'unknown'}"
            task_data = {'task_id': task_id, 'text': text, 'voice': voice, 'user_id': user_id, 'priority': priority, 'created_at': time.time()}
            self.redis_client.xadd(self.stream_name, {'data': json.dumps(task_data)})
            self.stats['total_tasks'] += 1
            logger.info(f'Task {task_id} submitted to GPU worker pool')
            return task_id
        except Exception:
            logger.exception('Error submitting task')
            raise

    async def get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Получение результата задачи"""
        if task_id in self.completed_tasks:
            task = self.completed_tasks[task_id]
            return {'task_id': task.task_id, 'status': 'completed' if task.result_path else 'failed', 'result_path': task.result_path, 'error': task.error, 'processing_time': task.completed_at - task.started_at if task.completed_at and task.started_at else 0}
        return None

    async def stop(self):
        """Остановка пула воркеров"""
        logger.info('Stopping GPU worker pool...')
        self.running = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        for task in self.worker_tasks:
            task.cancel()
        if self.worker_tasks:
            await asyncio.gather(*self.worker_tasks, return_exceptions=True)
        self.worker_tasks.clear()
        if self.redis_client:
            self.redis_client.close()
        logger.info('GPU worker pool stopped')

    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики пула воркеров"""
        return {**self.stats, 'active_workers': len(self.worker_tasks), 'device': self.device, 'gpu_metrics': self._last_gpu_metrics.__dict__ if self._last_gpu_metrics else None}

    def get_gpu_metrics(self) -> Optional[GPUMetrics]:
        """Получение текущих метрик GPU"""
        return self._last_gpu_metrics
try:
    from gpu_config import gpu_config
    gpu_worker_pool = GPUWorkerPool(config=gpu_config)
except ImportError:
    gpu_worker_pool = GPUWorkerPool()
