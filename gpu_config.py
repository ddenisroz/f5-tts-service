import os
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class GPUConfig:
    """Конфигурация GPU Worker Pool"""
    redis_url: str = 'redis://localhost:6379/0'
    input_stream: str = 'tts_requests'
    output_stream: str = 'tts_results'
    gpu_stream: str = 'gpu_tts_requests'
    gpu_results_stream: str = 'gpu_tts_results'
    consumer_group: str = 'gpu_workers'
    min_concurrent: int = 1
    max_concurrent: int = 4
    initial_concurrent: int = 2
    gpu_memory_threshold_low: float = 0.3
    gpu_memory_threshold_high: float = 0.8
    gpu_memory_threshold_critical: float = 0.9
    monitoring_interval: float = 5.0
    health_history_size: int = 100
    task_timeout: float = 300.0
    batch_size: int = 10
    retry_attempts: int = 3
    retry_delay: float = 5.0
    alert_thresholds: Dict[str, float] = None

    def __post_init__(self):
        if self.alert_thresholds is None:
            self.alert_thresholds = {'memory_usage_critical': 0.9, 'memory_usage_warning': 0.8, 'temperature_critical': 85.0, 'temperature_warning': 80.0, 'error_rate_critical': 0.1, 'error_rate_warning': 0.05, 'health_score_critical': 30.0, 'health_score_warning': 50.0}

    @classmethod
    def from_env(cls) -> 'GPUConfig':
        """Создание конфигурации из переменных окружения"""
        return cls(redis_url=os.getenv('GPU_REDIS_URL', 'redis://localhost:6379/0'), input_stream=os.getenv('GPU_INPUT_STREAM', 'tts_requests'), output_stream=os.getenv('GPU_OUTPUT_STREAM', 'tts_results'), gpu_stream=os.getenv('GPU_STREAM', 'gpu_tts_requests'), gpu_results_stream=os.getenv('GPU_RESULTS_STREAM', 'gpu_tts_results'), consumer_group=os.getenv('GPU_CONSUMER_GROUP', 'gpu_workers'), min_concurrent=int(os.getenv('GPU_MIN_CONCURRENT', '1')), max_concurrent=int(os.getenv('GPU_MAX_CONCURRENT', '4')), initial_concurrent=int(os.getenv('GPU_INITIAL_CONCURRENT', '2')), gpu_memory_threshold_low=float(os.getenv('GPU_MEMORY_THRESHOLD_LOW', '0.3')), gpu_memory_threshold_high=float(os.getenv('GPU_MEMORY_THRESHOLD_HIGH', '0.8')), gpu_memory_threshold_critical=float(os.getenv('GPU_MEMORY_THRESHOLD_CRITICAL', '0.9')), monitoring_interval=float(os.getenv('GPU_MONITORING_INTERVAL', '5.0')), health_history_size=int(os.getenv('GPU_HEALTH_HISTORY_SIZE', '100')), task_timeout=float(os.getenv('GPU_TASK_TIMEOUT', '300.0')), batch_size=int(os.getenv('GPU_BATCH_SIZE', '10')), retry_attempts=int(os.getenv('GPU_RETRY_ATTEMPTS', '3')), retry_delay=float(os.getenv('GPU_RETRY_DELAY', '5.0')))

    def to_dict(self) -> Dict[str, Any]:
        """Преобразование конфигурации в словарь"""
        return {'redis_url': self.redis_url, 'input_stream': self.input_stream, 'output_stream': self.output_stream, 'gpu_stream': self.gpu_stream, 'gpu_results_stream': self.gpu_results_stream, 'consumer_group': self.consumer_group, 'min_concurrent': self.min_concurrent, 'max_concurrent': self.max_concurrent, 'initial_concurrent': self.initial_concurrent, 'gpu_memory_threshold_low': self.gpu_memory_threshold_low, 'gpu_memory_threshold_high': self.gpu_memory_threshold_high, 'gpu_memory_threshold_critical': self.gpu_memory_threshold_critical, 'monitoring_interval': self.monitoring_interval, 'health_history_size': self.health_history_size, 'task_timeout': self.task_timeout, 'batch_size': self.batch_size, 'retry_attempts': self.retry_attempts, 'retry_delay': self.retry_delay, 'alert_thresholds': self.alert_thresholds}

    def validate(self) -> bool:
        """Валидация конфигурации"""
        errors = []
        if self.min_concurrent < 1:
            errors.append('min_concurrent must be >= 1')
        if self.max_concurrent < self.min_concurrent:
            errors.append('max_concurrent must be >= min_concurrent')
        if self.initial_concurrent < self.min_concurrent or self.initial_concurrent > self.max_concurrent:
            errors.append('initial_concurrent must be between min_concurrent and max_concurrent')
        if not 0 <= self.gpu_memory_threshold_low <= 1:
            errors.append('gpu_memory_threshold_low must be between 0 and 1')
        if not 0 <= self.gpu_memory_threshold_high <= 1:
            errors.append('gpu_memory_threshold_high must be between 0 and 1')
        if not 0 <= self.gpu_memory_threshold_critical <= 1:
            errors.append('gpu_memory_threshold_critical must be between 0 and 1')
        if not self.gpu_memory_threshold_low <= self.gpu_memory_threshold_high <= self.gpu_memory_threshold_critical:
            errors.append('Memory thresholds must be in ascending order')
        if self.monitoring_interval <= 0:
            errors.append('monitoring_interval must be > 0')
        if self.task_timeout <= 0:
            errors.append('task_timeout must be > 0')
        if self.retry_delay <= 0:
            errors.append('retry_delay must be > 0')
        if errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")
        return True
gpu_config = GPUConfig.from_env()
try:
    gpu_config.validate()
except ValueError as e:
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f'GPU configuration validation warning: {e}')
