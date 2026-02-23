import asyncio
import logging
import json
import time
from typing import Dict, Optional, Any, List
from dataclasses import dataclass
import redis
logger = logging.getLogger(__name__)

@dataclass
class GPUIntegrationConfig:
    """Конфигурация интеграции GPU Worker Pool"""
    redis_url: str = 'redis://localhost:6379/0'
    input_stream: str = 'tts_requests'
    output_stream: str = 'tts_results'
    gpu_stream: str = 'gpu_tts_requests'
    gpu_results_stream: str = 'gpu_tts_results'
    consumer_group: str = 'gpu_integration'
    batch_size: int = 10
    processing_timeout: float = 300.0
    retry_attempts: int = 3
    retry_delay: float = 5.0

class GPUIntegrationService:
    """
    Сервис интеграции GPU Worker Pool с существующей Redis архитектурой
    """

    def __init__(self, config: Optional[GPUIntegrationConfig]=None):
        self.config = config or GPUIntegrationConfig()
        self.redis_client = None
        self.running = False
        self._worker_tasks: List[asyncio.Task] = []
        self.stats = {'tasks_processed': 0, 'tasks_forwarded_to_gpu': 0, 'tasks_completed': 0, 'tasks_failed': 0, 'gpu_utilization': 0.0, 'avg_processing_time': 0.0, 'last_activity': None}
        self.task_cache: Dict[str, Dict[str, Any]] = {}

    async def initialize(self):
        """Text cleaned."""
        try:
            await self._connect_redis()
            await self._setup_consumer_groups()
            await self._start_workers()
            self.running = True
            logger.info('GPU Integration Service initialized successfully')
        except Exception:
            logger.exception('Failed to initialize GPU Integration Service')
            raise

    async def _connect_redis(self):
        """Подключение к Redis"""
        try:
            self.redis_client = redis.from_url(self.config.redis_url, decode_responses=True)
            await asyncio.get_event_loop().run_in_executor(None, self.redis_client.ping)
            logger.info(f'Connected to Redis: {self.config.redis_url}')
        except Exception:
            logger.exception('Failed to connect to Redis')
            raise

    async def _setup_consumer_groups(self):
        """Настройка consumer groups"""
        try:
            streams = [self.config.input_stream, self.config.gpu_results_stream]
            for stream in streams:
                try:
                    await asyncio.get_event_loop().run_in_executor(None, self.redis_client.xgroup_create, stream, self.config.consumer_group, id='0', mkstream=True)
                except redis.exceptions.ResponseError as e:
                    if 'BUSYGROUP' not in str(e):
                        raise
            logger.info('Consumer groups setup completed')
        except Exception:
            logger.exception('Failed to setup consumer groups')
            raise

    async def _start_workers(self):
        """Запуск воркеров для обработки задач"""
        input_worker = asyncio.create_task(self._input_worker())
        self._worker_tasks.append(input_worker)
        result_worker = asyncio.create_task(self._result_worker())
        self._worker_tasks.append(result_worker)
        logger.info('GPU Integration workers started')

    async def _input_worker(self):
        """Воркер для обработки входящих TTS задач"""
        logger.info('Input worker started')
        while self.running:
            try:
                messages = await asyncio.get_event_loop().run_in_executor(None, self._get_input_tasks)
                if not messages:
                    await asyncio.sleep(1)
                    continue
                for (stream_id, fields) in messages:
                    await self._process_input_task(stream_id, fields)
            except Exception:
                logger.exception('Error in input worker')
                await asyncio.sleep(5)

    def _get_input_tasks(self):
        """Получение задач из входящего stream"""
        try:
            messages = self.redis_client.xreadgroup(self.config.consumer_group, 'input_worker', {self.config.input_stream: '>'}, count=self.config.batch_size, block=1000)
            return messages[0][1] if messages else []
        except Exception:
            logger.exception('Error reading input tasks')
            return []

    async def _process_input_task(self, stream_id: str, fields: Dict[str, str]):
        """Обработка входящей TTS задачи"""
        try:
            task_data = json.loads(fields.get('data', '{}'))
            task_id = task_data.get('task_id', stream_id)
            logger.info(f'Processing input task: {task_id}')
            use_gpu = await self._should_use_gpu(task_data)
            if use_gpu:
                await self._forward_to_gpu(task_id, task_data, stream_id)
            else:
                await self._process_on_cpu(task_id, task_data, stream_id)
            self.stats['tasks_processed'] += 1
            self.stats['last_activity'] = time.time()
        except Exception:
            logger.exception('Error processing input task {stream_id}')
            try:
                self.redis_client.xack(self.config.input_stream, self.config.consumer_group, stream_id)
            except Exception:
                pass

    async def _should_use_gpu(self, task_data: Dict[str, Any]) -> bool:
        """Определение, нужно ли использовать GPU для задачи"""
        try:
            from gpu_worker_pool import gpu_worker_pool
            if not hasattr(gpu_worker_pool, 'running') or not gpu_worker_pool.running:
                return False
            gpu_metrics = gpu_worker_pool.get_gpu_metrics()
            if gpu_metrics and gpu_metrics.memory_usage_percent > 0.95:
                return False
            priority = task_data.get('priority', 0)
            if priority < 0:
                return False
            text = task_data.get('text', '')
            if len(text) < 50:
                return False
            return True
        except Exception:
            logger.exception('Error checking GPU availability')
            return False

    async def _forward_to_gpu(self, task_id: str, task_data: Dict[str, Any], stream_id: str):
        """Перенаправление задачи на GPU Worker Pool"""
        try:
            gpu_task_data = {'original_task_id': task_id, 'original_stream_id': stream_id, 'data': json.dumps(task_data)}
            self.redis_client.xadd(self.config.gpu_stream, gpu_task_data)
            self.task_cache[task_id] = {'stream_id': stream_id, 'started_at': time.time(), 'status': 'forwarded_to_gpu'}
            self.stats['tasks_forwarded_to_gpu'] += 1
            logger.info(f'Task {task_id} forwarded to GPU')
        except Exception:
            logger.exception('Error forwarding task to GPU')
            raise

    async def _process_on_cpu(self, task_id: str, task_data: Dict[str, Any], stream_id: str):
        """Обработка задачи на CPU (fallback)"""
        try:
            from tts_engine import tts_engine_manager
            if not tts_engine_manager.is_ready():
                raise RuntimeError('TTS engine not ready')
            text = task_data.get('text', '')
            voice = task_data.get('voice', 'female_1')
            user_id = task_data.get('user_id')
            result_path = await tts_engine_manager.synthesize_speech_async(text=text, voice=voice, user_id=user_id)
            await self._send_result(task_id, result_path, None, stream_id)
            self.redis_client.xack(self.config.input_stream, self.config.consumer_group, stream_id)
            logger.info(f'Task {task_id} processed on CPU')
        except Exception as e:
            logger.exception('Error processing task on CPU')
            await self._send_result(task_id, None, str(e), stream_id)
            self.redis_client.xack(self.config.input_stream, self.config.consumer_group, stream_id)

    async def _result_worker(self):
        """Воркер для обработки результатов от GPU"""
        logger.info('Result worker started')
        while self.running:
            try:
                messages = await asyncio.get_event_loop().run_in_executor(None, self._get_gpu_results)
                if not messages:
                    await asyncio.sleep(1)
                    continue
                for (stream_id, fields) in messages:
                    await self._process_gpu_result(stream_id, fields)
            except Exception:
                logger.exception('Error in result worker')
                await asyncio.sleep(5)

    def _get_gpu_results(self):
        """Получение результатов от GPU"""
        try:
            messages = self.redis_client.xreadgroup(self.config.consumer_group, 'result_worker', {self.config.gpu_results_stream: '>'}, count=self.config.batch_size, block=1000)
            return messages[0][1] if messages else []
        except Exception:
            logger.exception('Error reading GPU results')
            return []

    async def _process_gpu_result(self, stream_id: str, fields: Dict[str, str]):
        """Обработка результата от GPU"""
        try:
            result_data = json.loads(fields.get('data', '{}'))
            task_id = result_data.get('task_id', '')
            logger.info(f'Processing GPU result for task: {task_id}')
            if task_id in self.task_cache:
                task_info = self.task_cache[task_id]
                original_stream_id = task_info['stream_id']
                result_path = result_data.get('result_path')
                error = result_data.get('error')
                await self._send_result(task_id, result_path, error, original_stream_id)
                self.redis_client.xack(self.config.input_stream, self.config.consumer_group, original_stream_id)
                del self.task_cache[task_id]
                if result_path:
                    self.stats['tasks_completed'] += 1
                else:
                    self.stats['tasks_failed'] += 1
                logger.info(f'GPU result processed for task {task_id}')
            else:
                logger.warning(f'No cache entry found for task {task_id}')
            self.redis_client.xack(self.config.gpu_results_stream, self.config.consumer_group, stream_id)
        except Exception:
            logger.exception('Error processing GPU result')
            try:
                self.redis_client.xack(self.config.gpu_results_stream, self.config.consumer_group, stream_id)
            except Exception:
                pass

    async def _send_result(self, task_id: str, result_path: Optional[str], error: Optional[str], stream_id: str):
        """Отправка результата в output stream"""
        try:
            result_data = {'task_id': task_id, 'status': 'completed' if result_path else 'failed', 'result_path': result_path or '', 'error': error or '', 'processing_time': time.time() - self.task_cache.get(task_id, {}).get('started_at', time.time()), 'completed_at': time.time()}
            self.redis_client.xadd(self.config.output_stream, result_data)
            logger.info(f'Result sent for task {task_id}')
        except Exception:
            logger.exception('Error sending result')

    async def stop(self):
        """Остановка сервиса интеграции"""
        logger.info('Stopping GPU Integration Service...')
        self.running = False
        for task in self._worker_tasks:
            task.cancel()
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()
        if self.redis_client:
            self.redis_client.close()
        logger.info('GPU Integration Service stopped')

    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики сервиса"""
        return {**self.stats, 'cached_tasks': len(self.task_cache), 'running': self.running, 'config': {'input_stream': self.config.input_stream, 'output_stream': self.config.output_stream, 'gpu_stream': self.config.gpu_stream, 'batch_size': self.config.batch_size}}

    def get_cached_tasks(self) -> Dict[str, Dict[str, Any]]:
        """Получение кэшированных задач"""
        return self.task_cache.copy()
gpu_integration_service = GPUIntegrationService()
