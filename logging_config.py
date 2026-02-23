# F5_tts/logging_config.py
import os
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime
import sys

class LoggingConfig:
    """Централизованная конфигурация логирования для TTS сервиса"""
    
    def __init__(self, service_name: str = "f5_tts"):
        self.service_name = service_name
        repo_root = Path(__file__).resolve().parents[1]
        logs_root = os.getenv("LOG_DIR")
        self.logs_dir = Path(logs_root) if logs_root else (repo_root / "logs")
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Создаем подпапки для разных типов логов
        self.app_logs_dir = self.logs_dir / "app"
        self.error_logs_dir = self.logs_dir / "errors"
        self.tts_logs_dir = self.logs_dir / "tts"
        self.audio_logs_dir = self.logs_dir / "audio"
        
        for dir_path in [self.app_logs_dir, self.error_logs_dir, self.tts_logs_dir, self.audio_logs_dir]:
            dir_path.mkdir(exist_ok=True)
    
    def setup_logging(self, log_level: str = "INFO"):
        """Настройка логирования для TTS сервиса"""
        
        # Получаем уровень логирования
        level = getattr(logging, log_level.upper(), logging.INFO)
        
        # Создаем форматтеры
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        simple_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Основной логгер приложения
        app_logger = logging.getLogger(self.service_name)
        app_logger.setLevel(level)
        
        # Очищаем существующие обработчики
        app_logger.handlers.clear()
        
        # 1. Ротация логов по дням (максимум 30 дней)
        daily_handler = logging.handlers.TimedRotatingFileHandler(
            filename=self.app_logs_dir / f"{self.service_name}.log",
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        daily_handler.setFormatter(detailed_formatter)
        daily_handler.setLevel(level)
        app_logger.addHandler(daily_handler)

        # 1b. Единый лог в корневой logs/ для внешних инструментов
        root_log_handler = logging.handlers.TimedRotatingFileHandler(
            filename=self.logs_dir / f"{self.service_name}.log",
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        root_log_handler.setFormatter(detailed_formatter)
        root_log_handler.setLevel(level)
        app_logger.addHandler(root_log_handler)
        
        # 2. Отдельный файл для ошибок
        error_handler = logging.handlers.TimedRotatingFileHandler(
            filename=self.error_logs_dir / f"{self.service_name}_errors.log",
            when='midnight',
            interval=1,
            backupCount=90,  # Ошибки храним дольше
            encoding='utf-8'
        )
        error_handler.setFormatter(detailed_formatter)
        error_handler.setLevel(logging.ERROR)
        app_logger.addHandler(error_handler)
        
        # 3. Консольный вывод
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(simple_formatter)
        console_handler.setLevel(logging.INFO)
        app_logger.addHandler(console_handler)
        
        # 4. Логгер для TTS операций
        tts_logger = logging.getLogger(f"{self.service_name}.tts")
        tts_logger.setLevel(logging.INFO)
        
        tts_handler = logging.handlers.TimedRotatingFileHandler(
            filename=self.tts_logs_dir / f"{self.service_name}_tts.log",
            when='midnight',
            interval=1,
            backupCount=7,  # TTS логи храним неделю
            encoding='utf-8'
        )
        tts_handler.setFormatter(detailed_formatter)
        tts_logger.addHandler(tts_handler)
        
        # 5. Логгер для аудио операций
        audio_logger = logging.getLogger(f"{self.service_name}.audio")
        audio_logger.setLevel(logging.INFO)
        
        audio_handler = logging.handlers.TimedRotatingFileHandler(
            filename=self.audio_logs_dir / f"{self.service_name}_audio.log",
            when='midnight',
            interval=1,
            backupCount=7,  # Аудио логи храним неделю
            encoding='utf-8'
        )
        audio_handler.setFormatter(detailed_formatter)
        audio_logger.addHandler(audio_handler)
        
        # Настройка внешних библиотек
        logging.getLogger("uvicorn").setLevel(logging.WARNING)
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("fastapi").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("transformers").setLevel(logging.WARNING)
        logging.getLogger("torch").setLevel(logging.WARNING)
        
        return app_logger
    
    def get_tts_logger(self):
        """Получить логгер для TTS операций"""
        return logging.getLogger(f"{self.service_name}.tts")
    
    def get_audio_logger(self):
        """Получить логгер для аудио операций"""
        return logging.getLogger(f"{self.service_name}.audio")

# Глобальный экземпляр
tts_logging_config = LoggingConfig("f5_tts")

