import psutil
import time
import logging
from datetime import datetime
from typing import Dict, Any
import threading
import json
from pathlib import Path
logger = logging.getLogger('f5_tts.monitoring')

class SystemMonitor:
    """Мониторинг системных ресурсов для TTS сервиса"""

    def __init__(self, service_name: str='f5_tts'):
        self.service_name = service_name
        self.monitoring_data = []
        self.is_monitoring = False
        self.monitor_thread = None
        self.start_time = time.time()
        self.monitoring_dir = Path('logs/monitoring')
        self.monitoring_dir.mkdir(parents=True, exist_ok=True)

    def get_system_info(self) -> Dict[str, Any]:
        """Получение информации о системных ресурсах"""
        try:
            process = psutil.Process()
            cpu_percent = process.cpu_percent(interval=1)
            memory_info = process.memory_info()
            memory_percent = process.memory_percent()
            system_cpu = psutil.cpu_percent(interval=1)
            system_memory = psutil.virtual_memory()
            system_disk = psutil.disk_usage('/')
            uptime = time.time() - self.start_time
            gpu_info = self._get_gpu_info()
            return {'timestamp': datetime.now().isoformat(), 'service': self.service_name, 'uptime_seconds': uptime, 'uptime_formatted': self._format_uptime(uptime), 'process': {'pid': process.pid, 'cpu_percent': round(cpu_percent, 2), 'memory_mb': round(memory_info.rss / 1024 / 1024, 2), 'memory_percent': round(memory_percent, 2), 'threads': process.num_threads(), 'open_files': len(process.open_files()), 'connections': len(process.connections())}, 'system': {'cpu_percent': round(system_cpu, 2), 'memory_total_gb': round(system_memory.total / 1024 / 1024 / 1024, 2), 'memory_used_gb': round(system_memory.used / 1024 / 1024 / 1024, 2), 'memory_percent': round(system_memory.percent, 2), 'disk_total_gb': round(system_disk.total / 1024 / 1024 / 1024, 2), 'disk_used_gb': round(system_disk.used / 1024 / 1024 / 1024, 2), 'disk_percent': round(system_disk.percent, 2)}, 'gpu': gpu_info}
        except Exception:
            logger.exception('Error getting system info')
            return {'error': 'Internal server error'}

    def _get_gpu_info(self) -> Dict[str, Any]:
        """Получение информации о GPU"""
        try:
            import subprocess
            result = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                gpu_data = result.stdout.strip().split(', ')
                return {'gpu_utilization_percent': int(gpu_data[0]) if gpu_data[0] != 'N/A' else 0, 'gpu_memory_used_mb': int(gpu_data[1]) if gpu_data[1] != 'N/A' else 0, 'gpu_memory_total_mb': int(gpu_data[2]) if gpu_data[2] != 'N/A' else 0, 'gpu_temperature_c': int(gpu_data[3]) if gpu_data[3] != 'N/A' else 0}
        except Exception:
            logger.exception('GPU info not available')
        return {'gpu_utilization_percent': 0, 'gpu_memory_used_mb': 0, 'gpu_memory_total_mb': 0, 'gpu_temperature_c': 0, 'gpu_available': False}

    def _format_uptime(self, seconds: float) -> str:
        """Форматирование времени работы"""
        hours = int(seconds // 3600)
        minutes = int(seconds % 3600 // 60)
        seconds = int(seconds % 60)
        return f'{hours:02d}:{minutes:02d}:{seconds:02d}'

    def start_monitoring(self, interval: int=60):
        """Запуск мониторинга в фоновом режиме"""
        if self.is_monitoring:
            return
        self.is_monitoring = True

        def monitor_loop():
            while self.is_monitoring:
                try:
                    data = self.get_system_info()
                    self.monitoring_data.append(data)
                    max_entries = 24 * 60
                    if len(self.monitoring_data) > max_entries:
                        self.monitoring_data = self.monitoring_data[-max_entries:]
                    if len(self.monitoring_data) % 60 == 0:
                        self._save_monitoring_data()
                    logger.debug(f"TTS Monitoring data collected: CPU {data['process']['cpu_percent']}%, Memory {data['process']['memory_mb']}MB, GPU {data['gpu']['gpu_utilization_percent']}%")
                except Exception:
                    logger.exception('Error in TTS monitoring loop')
                time.sleep(interval)
        self.monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info(f'TTS System monitoring started for {self.service_name}')

    def stop_monitoring(self):
        """Остановка мониторинга"""
        self.is_monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        self._save_monitoring_data()
        logger.info(f'TTS System monitoring stopped for {self.service_name}')

    def _save_monitoring_data(self):
        """Сохранение данных мониторинга в файл"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H')
            filename = self.monitoring_dir / f'{self.service_name}_monitoring_{timestamp}.json'
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.monitoring_data, f, indent=2, ensure_ascii=False)
            logger.debug(f'TTS Monitoring data saved to {filename}')
        except Exception:
            logger.exception('Error saving TTS monitoring data')

    def get_current_stats(self) -> Dict[str, Any]:
        """Получение текущей статистики"""
        if not self.monitoring_data:
            return self.get_system_info()
        latest = self.monitoring_data[-1]
        recent_data = self.monitoring_data[-60:] if len(self.monitoring_data) >= 60 else self.monitoring_data
        avg_cpu = sum((d['process']['cpu_percent'] for d in recent_data)) / len(recent_data)
        avg_memory = sum((d['process']['memory_mb'] for d in recent_data)) / len(recent_data)
        avg_gpu = sum((d['gpu']['gpu_utilization_percent'] for d in recent_data)) / len(recent_data)
        return {**latest, 'averages': {'cpu_percent_1h': round(avg_cpu, 2), 'memory_mb_1h': round(avg_memory, 2), 'gpu_percent_1h': round(avg_gpu, 2)}}

    def get_monitoring_summary(self) -> Dict[str, Any]:
        """Получение сводки мониторинга"""
        if not self.monitoring_data:
            return {'message': 'No monitoring data available'}
        data_24h = self.monitoring_data[-1440:] if len(self.monitoring_data) >= 1440 else self.monitoring_data
        cpu_values = [d['process']['cpu_percent'] for d in data_24h]
        memory_values = [d['process']['memory_mb'] for d in data_24h]
        gpu_values = [d['gpu']['gpu_utilization_percent'] for d in data_24h]
        return {'service': self.service_name, 'monitoring_period': f'{len(data_24h)} records', 'time_range': {'start': data_24h[0]['timestamp'] if data_24h else None, 'end': data_24h[-1]['timestamp'] if data_24h else None}, 'cpu_stats': {'min': round(min(cpu_values), 2), 'max': round(max(cpu_values), 2), 'avg': round(sum(cpu_values) / len(cpu_values), 2)}, 'memory_stats': {'min_mb': round(min(memory_values), 2), 'max_mb': round(max(memory_values), 2), 'avg_mb': round(sum(memory_values) / len(memory_values), 2)}, 'gpu_stats': {'min': round(min(gpu_values), 2), 'max': round(max(gpu_values), 2), 'avg': round(sum(gpu_values) / len(gpu_values), 2)}, 'current': self.get_current_stats()}
tts_monitor = SystemMonitor('f5_tts')
