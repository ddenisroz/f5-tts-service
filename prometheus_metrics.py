import time
import asyncio
import logging
import torch
from typing import Dict, Any, Optional
from prometheus_client import Counter, Histogram, Gauge, Summary, start_http_server
import psutil
import threading
logger = logging.getLogger(__name__)

class TTSPrometheusMetrics:
    """
    Prometheus метрики для TTS сервиса с GPU мониторингом
    """

    def __init__(self, port: int=8003):
        self.port = port
        self.server_started = False
        self.monitoring_thread = None
        self.running = False
        self.tts_requests_total = Counter('tts_requests_total', 'Total number of TTS requests', ['voice', 'platform', 'status', 'processing_type'])
        self.tts_requests_by_user = Counter('tts_requests_by_user_total', 'TTS requests by user', ['user_id', 'platform'])
        self.tts_synthesis_duration = Histogram('tts_synthesis_duration_seconds', 'Time spent on TTS synthesis', ['voice', 'platform', 'processing_type'], buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0])
        self.tts_synthesis_duration_summary = Summary('tts_synthesis_duration_summary_seconds', 'Summary of TTS synthesis time', ['voice', 'platform', 'processing_type'])
        self.tts_synthesis_errors = Counter('tts_synthesis_errors_total', 'Total number of TTS synthesis errors', ['voice', 'platform', 'error_type'])
        self.gpu_usage = Gauge('gpu_usage_percent', 'GPU usage percentage', ['device_id'])
        self.gpu_memory_used = Gauge('gpu_memory_used_bytes', 'GPU memory used in bytes', ['device_id'])
        self.gpu_memory_total = Gauge('gpu_memory_total_bytes', 'GPU total memory in bytes', ['device_id'])
        self.gpu_memory_percent = Gauge('gpu_memory_usage_percent', 'GPU memory usage percentage', ['device_id'])
        self.gpu_temperature = Gauge('gpu_temperature_celsius', 'GPU temperature in Celsius', ['device_id'])
        self.gpu_power_usage = Gauge('gpu_power_usage_watts', 'GPU power usage in watts', ['device_id'])
        self.gpu_workers_active = Gauge('gpu_workers_active', 'Number of active GPU workers')
        self.gpu_workers_concurrent = Gauge('gpu_workers_concurrent', 'Current concurrent GPU workers')
        self.gpu_tasks_processed = Counter('gpu_tasks_processed_total', 'Total GPU tasks processed', ['status'])
        self.gpu_task_processing_time = Histogram('gpu_task_processing_duration_seconds', 'GPU task processing duration', ['task_type'], buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0])
        self.async_workers_active = Gauge('async_workers_active', 'Number of active async workers')
        self.async_workers_total = Gauge('async_workers_total', 'Total number of async workers')
        self.async_queue_size = Gauge('async_queue_size', 'Size of async worker queues', ['priority'])
        self.async_tasks_processed = Counter('async_tasks_processed_total', 'Total async tasks processed', ['status', 'processing_type'])
        self.async_task_processing_time = Histogram('async_task_processing_duration_seconds', 'Async task processing duration', ['priority', 'processing_type'], buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0])
        self.system_cpu_usage = Gauge('system_cpu_usage_percent', 'System CPU usage percentage')
        self.system_memory_usage = Gauge('system_memory_usage_bytes', 'System memory usage in bytes')
        self.system_memory_percent = Gauge('system_memory_usage_percent', 'System memory usage percentage')
        self.process_cpu_usage = Gauge('process_cpu_usage_percent', 'Process CPU usage percentage')
        self.process_memory_usage = Gauge('process_memory_usage_bytes', 'Process memory usage in bytes')
        self.errors_total = Counter('tts_errors_total', 'Total number of errors', ['service', 'error_type', 'component'])
        self.api_requests_total = Counter('tts_api_requests_total', 'Total API requests', ['method', 'endpoint', 'status_code'])
        self.api_request_duration = Histogram('tts_api_request_duration_seconds', 'API request duration', ['method', 'endpoint'], buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0])
        self.redis_connections = Gauge('redis_connections_active', 'Active Redis connections')
        self.redis_queue_length = Gauge('redis_queue_length', 'Redis queue length', ['queue_name'])

    def start_server(self):
        """Запуск Prometheus HTTP сервера"""
        if not self.server_started:
            start_http_server(self.port)
            self.server_started = True
            logger.info(f'TTS Prometheus metrics server started on port {self.port}')

    def start_monitoring(self, interval: float=5.0):
        """Запуск мониторинга метрик"""
        if self.running:
            return
        self.running = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, args=(interval,), daemon=True)
        self.monitoring_thread.start()
        logger.info(f'TTS Prometheus monitoring started with {interval}s interval')

    def stop_monitoring(self):
        """Остановка мониторинга"""
        self.running = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        logger.info('TTS Prometheus monitoring stopped')

    def _monitoring_loop(self, interval: float):
        """Основной цикл мониторинга"""
        while self.running:
            try:
                self._update_gpu_metrics()
                self._update_system_metrics()
                self._update_worker_metrics()
                self._update_redis_metrics()
            except Exception:
                logger.exception('Error in Prometheus monitoring loop')
            time.sleep(interval)

    def _update_gpu_metrics(self):
        """Обновление GPU метрик"""
        try:
            if not torch.cuda.is_available():
                return
            device_count = torch.cuda.device_count()
            for device_id in range(device_count):
                device_name = f'cuda:{device_id}'
                try:
                    gpu_usage = torch.cuda.utilization(device_id)
                    self.gpu_usage.labels(device_id=device_id).set(gpu_usage)
                except Exception:
                    logger.exception('Could not get GPU utilization for device %s', device_id)
                try:
                    memory_allocated = torch.cuda.memory_allocated(device_id)
                    memory_reserved = torch.cuda.memory_reserved(device_id)
                    memory_total = torch.cuda.get_device_properties(device_id).total_memory
                    memory_percent = memory_allocated / memory_total * 100
                    self.gpu_memory_used.labels(device_id=device_id).set(memory_allocated)
                    self.gpu_memory_total.labels(device_id=device_id).set(memory_total)
                    self.gpu_memory_percent.labels(device_id=device_id).set(memory_percent)
                except Exception:
                    logger.exception('Could not get GPU memory info for device %s', device_id)
                try:
                    import pynvml
                    pynvml.nvmlInit()
                    handle = pynvml.nvmlDeviceGetHandleByIndex(device_id)
                    try:
                        temperature = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                        self.gpu_temperature.labels(device_id=device_id).set(temperature)
                    except Exception:
                        pass
                    try:
                        power_usage = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
                        self.gpu_power_usage.labels(device_id=device_id).set(power_usage)
                    except Exception:
                        pass
                except ImportError:
                    pass
                except Exception:
                    logger.exception('Could not get GPU temperature/power for device %s', device_id)
        except Exception:
            logger.exception('Error updating GPU metrics')

    def _update_system_metrics(self):
        """Обновление системных метрик"""
        try:
            system_cpu = psutil.cpu_percent(interval=1)
            system_memory = psutil.virtual_memory()
            self.system_cpu_usage.set(system_cpu)
            self.system_memory_usage.set(system_memory.used)
            self.system_memory_percent.set(system_memory.percent)
            process = psutil.Process()
            process_cpu = process.cpu_percent()
            process_memory = process.memory_info()
            self.process_cpu_usage.set(process_cpu)
            self.process_memory_usage.set(process_memory.rss)
        except Exception:
            logger.exception('Error updating system metrics')

    def _update_worker_metrics(self):
        """Обновление метрик воркеров"""
        try:
            try:
                from gpu_worker_pool import gpu_worker_pool
                if hasattr(gpu_worker_pool, 'running') and gpu_worker_pool.running:
                    stats = gpu_worker_pool.get_stats()
                    self.gpu_workers_concurrent.set(stats.get('current_concurrent', 0))
            except Exception:
                logger.exception('Could not get GPU worker pool stats')
            try:
                from async_worker_manager import async_worker_manager
                if hasattr(async_worker_manager, 'running') and async_worker_manager.running:
                    stats = async_worker_manager.get_stats()
                    self.async_workers_active.set(stats.get('active_workers', 0))
                    self.async_workers_total.set(len(stats.get('workers', {})))
                    queue_sizes = async_worker_manager.get_queue_sizes()
                    for (priority, size) in queue_sizes.items():
                        self.async_queue_size.labels(priority=priority).set(size)
            except Exception:
                logger.exception('Could not get async worker manager stats')
        except Exception:
            logger.exception('Error updating worker metrics')

    def _update_redis_metrics(self):
        """Обновление Redis метрик"""
        try:
            import redis
            redis_client = redis.from_url('redis://localhost:6379/0', decode_responses=True)
            redis_client.ping()
            self.redis_connections.set(1)
            try:
                tts_requests_length = redis_client.xlen('tts_requests')
                self.redis_queue_length.labels(queue_name='tts_requests').set(tts_requests_length)
                tts_results_length = redis_client.xlen('tts_results')
                self.redis_queue_length.labels(queue_name='tts_results').set(tts_results_length)
                gpu_requests_length = redis_client.xlen('gpu_tts_requests')
                self.redis_queue_length.labels(queue_name='gpu_tts_requests').set(gpu_requests_length)
                gpu_results_length = redis_client.xlen('gpu_tts_results')
                self.redis_queue_length.labels(queue_name='gpu_tts_results').set(gpu_results_length)
            except Exception:
                logger.exception('Could not get Redis queue lengths')
        except Exception:
            logger.exception('Could not connect to Redis')
            self.redis_connections.set(0)

    def record_tts_request(self, voice: str, platform: str, status: str='success', processing_type: str='cpu'):
        """Записать TTS запрос"""
        self.tts_requests_total.labels(voice=voice, platform=platform, status=status, processing_type=processing_type).inc()

    def record_tts_request_by_user(self, user_id: int, platform: str):
        """Записать TTS запрос по пользователю"""
        self.tts_requests_by_user.labels(user_id=str(user_id), platform=platform).inc()

    def record_tts_synthesis_time(self, duration: float, voice: str, platform: str, processing_type: str='cpu'):
        """Записать время синтеза"""
        self.tts_synthesis_duration.labels(voice=voice, platform=platform, processing_type=processing_type).observe(duration)
        self.tts_synthesis_duration_summary.labels(voice=voice, platform=platform, processing_type=processing_type).observe(duration)

    def record_gpu_task(self, status: str='success'):
        """Записать GPU задачу"""
        self.gpu_tasks_processed.labels(status=status).inc()

    def record_gpu_task_time(self, duration: float, task_type: str='synthesis'):
        """Записать время обработки GPU задачи"""
        self.gpu_task_processing_time.labels(task_type=task_type).observe(duration)

    def record_async_task(self, status: str='success', processing_type: str='cpu', priority: str='NORMAL'):
        """Записать async задачу"""
        self.async_tasks_processed.labels(status=status, processing_type=processing_type).inc()

    def record_async_task_time(self, duration: float, priority: str='NORMAL', processing_type: str='cpu'):
        """Записать время обработки async задачи"""
        self.async_task_processing_time.labels(priority=priority, processing_type=processing_type).observe(duration)

    def record_error(self, service: str, error_type: str, component: str='unknown'):
        """Записать ошибку"""
        self.errors_total.labels(service=service, error_type=error_type, component=component).inc()

    def record_api_request(self, method: str, endpoint: str, status_code: int, duration: float=None):
        """Записать API запрос"""
        self.api_requests_total.labels(method=method, endpoint=endpoint, status_code=str(status_code)).inc()
        if duration is not None:
            self.api_request_duration.labels(method=method, endpoint=endpoint).observe(duration)

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Получить сводку метрик"""
        return {'prometheus_server': {'started': self.server_started, 'port': self.port}, 'monitoring': {'running': self.running, 'thread_alive': self.monitoring_thread.is_alive() if self.monitoring_thread else False}, 'gpu_available': torch.cuda.is_available(), 'gpu_device_count': torch.cuda.device_count() if torch.cuda.is_available() else 0}
tts_prometheus_metrics = TTSPrometheusMetrics()
