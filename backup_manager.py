# F5_tts/backup_manager.py
import os
import shutil
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional
import schedule
import threading
import time

class BackupManager:
    """Менеджер автоатических бэкапов для TTS сервиса"""
    
    def __init__(self, service_name: str = "f5_tts"):
        self.service_name = service_name
        self.logger = logging.getLogger(f"{service_name}.backup")
        
        #   
        self.backups_dir = Path("backups")
        self.backups_dir.mkdir(exist_ok=True)
        
        # Подпапки для разных типов бэкапов
        self.db_backups_dir = self.backups_dir / "database"
        self.config_backups_dir = self.backups_dir / "config"
        self.logs_backups_dir = self.backups_dir / "logs"
        self.audio_backups_dir = self.backups_dir / "audio"
        self.models_backups_dir = self.backups_dir / "models"
        
        for dir_path in [self.db_backups_dir, self.config_backups_dir, self.logs_backups_dir, 
                        self.audio_backups_dir, self.models_backups_dir]:
            dir_path.mkdir(exist_ok=True)
        
        #  
        self.max_db_backups = 30  # 
        self.max_config_backups = 7  # 
        self.max_logs_backups = 7  # 
        self.max_audio_backups = 3  # 
        self.max_models_backups = 1  # Дней (одели большие)
    
    def create_database_backup(self, db_path: str, backup_name: Optional[str] = None) -> str:
        """    TTS"""
        try:
            if not os.path.exists(db_path):
                self.logger.error(f"Database file not found: {db_path}")
                return None
            
            # Генерируе ия файла бэкапа
            if not backup_name:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_name = f"{self.service_name}_db_{timestamp}.db"
            
            backup_path = self.db_backups_dir / backup_name
            
            # File-level backup for single-file database snapshots.
            shutil.copy2(db_path, backup_path)
            
            self.logger.info(f"TTS Database backup created: {backup_path}")
            return str(backup_path)
            
        except Exception:
            self.logger.exception("Error creating TTS database backup")
            return None
    
    def create_config_backup(self, config_files: List[str]) -> str:
        """Создание бэкапа конфигурационных файлов TTS"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{self.service_name}_config_{timestamp}"
            backup_path = self.config_backups_dir / backup_name
            backup_path.mkdir(exist_ok=True)
            
            copied_files = []
            for config_file in config_files:
                if os.path.exists(config_file):
                    file_path = Path(config_file)
                    dest_path = backup_path / file_path.name
                    shutil.copy2(config_file, dest_path)
                    copied_files.append(str(dest_path))
            
            # Создае архив
            archive_path = f"{backup_path}.tar.gz"
            shutil.make_archive(str(backup_path), 'gztar', str(backup_path))
            shutil.rmtree(backup_path)  # Удаляе вреенную папку
            
            self.logger.info(f"TTS Config backup created: {archive_path}")
            return archive_path
            
        except Exception:
            self.logger.exception("Error creating TTS config backup")
            return None
    
    def create_logs_backup(self, logs_dir: str) -> str:
        """   TTS"""
        try:
            if not os.path.exists(logs_dir):
                self.logger.warning(f"TTS Logs directory not found: {logs_dir}")
                return None
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{self.service_name}_logs_{timestamp}"
            backup_path = self.logs_backups_dir / backup_name
            
            # Создае архив логов
            shutil.make_archive(str(backup_path), 'gztar', logs_dir)
            archive_path = f"{backup_path}.tar.gz"
            
            self.logger.info(f"TTS Logs backup created: {archive_path}")
            return archive_path
            
        except Exception:
            self.logger.exception("Error creating TTS logs backup")
            return None
    
    def create_audio_backup(self, audio_dir: str) -> str:
        """    TTS"""
        try:
            if not os.path.exists(audio_dir):
                self.logger.warning(f"TTS Audio directory not found: {audio_dir}")
                return None
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{self.service_name}_audio_{timestamp}"
            backup_path = self.audio_backups_dir / backup_name
            
            # Создае архив аудио
            shutil.make_archive(str(backup_path), 'gztar', audio_dir)
            archive_path = f"{backup_path}.tar.gz"
            
            self.logger.info(f"TTS Audio backup created: {archive_path}")
            return archive_path
            
        except Exception:
            self.logger.exception("Error creating TTS audio backup")
            return None
    
    def create_models_backup(self, models_dir: str) -> str:
        """Создание бэкапа оделей TTS (только етаданные)"""
        try:
            if not os.path.exists(models_dir):
                self.logger.warning(f"TTS Models directory not found: {models_dir}")
                return None
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{self.service_name}_models_meta_{timestamp}"
            backup_path = self.models_backups_dir / backup_name
            backup_path.mkdir(exist_ok=True)
            
            # экапи только етаданные оделей, не саи файлы
            models_path = Path(models_dir)
            for model_dir in models_path.iterdir():
                if model_dir.is_dir():
                    # Создае файл с инфорацией о одели
                    meta_file = backup_path / f"{model_dir.name}_meta.txt"
                    with open(meta_file, 'w', encoding='utf-8') as f:
                        f.write(f"Model: {model_dir.name}\n")
                        f.write(f"Path: {model_dir}\n")
                        f.write(f"Size: {sum(f.stat().st_size for f in model_dir.rglob('*') if f.is_file())} bytes\n")
                        f.write(f"Files count: {len(list(model_dir.rglob('*')))} files\n")
                        f.write(f"Backup created: {datetime.now().isoformat()}\n")
            
            # Создае архив етаданных
            archive_path = f"{backup_path}.tar.gz"
            shutil.make_archive(str(backup_path), 'gztar', str(backup_path))
            shutil.rmtree(backup_path)  # Удаляе вреенную папку
            
            self.logger.info(f"TTS Models metadata backup created: {archive_path}")
            return archive_path
            
        except Exception:
            self.logger.exception("Error creating TTS models backup")
            return None
    
    def cleanup_old_backups(self):
        """   TTS"""
        try:
            now = datetime.now()
            
            # Очистка бэкапов Д
            self._cleanup_directory(self.db_backups_dir, self.max_db_backups, now)
            
            #   
            self._cleanup_directory(self.config_backups_dir, self.max_config_backups, now)
            
            #   
            self._cleanup_directory(self.logs_backups_dir, self.max_logs_backups, now)
            
            #   
            self._cleanup_directory(self.audio_backups_dir, self.max_audio_backups, now)
            
            # Очистка бэкапов оделей
            self._cleanup_directory(self.models_backups_dir, self.max_models_backups, now)
            
            self.logger.info("TTS old backups cleanup completed")
            
        except Exception:
            self.logger.exception("Error during TTS cleanup")
    
    def _cleanup_directory(self, directory: Path, max_days: int, now: datetime):
        """     max_days """
        if not directory.exists():
            return
        
        cutoff_date = now - timedelta(days=max_days)
        
        for file_path in directory.iterdir():
            if file_path.is_file():
                file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_time < cutoff_date:
                    try:
                        file_path.unlink()
                        self.logger.info(f"Deleted old TTS backup: {file_path}")
                    except Exception:
                        self.logger.exception("Error deleting {file_path}")
    
    def get_backup_info(self) -> dict:
        """Получение инфорации о бэкапах TTS"""
        info = {
            "database_backups": [],
            "config_backups": [],
            "logs_backups": [],
            "audio_backups": [],
            "models_backups": []
        }
        
        for backup_type, directory in [
            ("database_backups", self.db_backups_dir),
            ("config_backups", self.config_backups_dir),
            ("logs_backups", self.logs_backups_dir),
            ("audio_backups", self.audio_backups_dir),
            ("models_backups", self.models_backups_dir)
        ]:
            if directory.exists():
                for file_path in directory.iterdir():
                    if file_path.is_file():
                        stat = file_path.stat()
                        info[backup_type].append({
                            "name": file_path.name,
                            "size": stat.st_size,
                            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                        })
        
        return info
    
    def schedule_backups(self):
        """Планирование автоатических бэкапов TTS"""
        # Ежедневный бэкап Д в 2:30
        schedule.every().day.at("02:30").do(self._daily_backup)
        
        # Еженедельный полный бэкап в воскресенье в 3:30
        schedule.every().sunday.at("03:30").do(self._weekly_backup)
        
        # Ежедневная очистка старых бэкапов в 4:30
        schedule.every().day.at("04:30").do(self.cleanup_old_backups)
        
        self.logger.info("TTS Backup schedule configured")
    
    def _daily_backup(self):
        """  TTS"""
        try:
            # Optional file backup path for legacy single-file DB setups.
            db_path = os.getenv("F5_TTS_DB_BACKUP_PATH", "").strip()
            if db_path and os.path.exists(db_path):
                self.create_database_backup(db_path)
            
            self.logger.info("TTS Daily backup completed")
        except Exception:
            self.logger.exception("Error in TTS daily backup")
    
    def _weekly_backup(self):
        """   TTS"""
        try:
            # Optional file backup path for legacy single-file DB setups.
            db_path = os.getenv("F5_TTS_DB_BACKUP_PATH", "").strip()
            if db_path and os.path.exists(db_path):
                self.create_database_backup(db_path)
            
            # экап конфигурации
            config_files = ["config.py", "requirements.txt"]
            self.create_config_backup(config_files)
            
            # экап логов
            self.create_logs_backup("logs")
            
            # экап аудио (только голоса)
            self.create_audio_backup("audio/voices")
            
            # экап етаданных оделей
            self.create_models_backup("f5_tts_cache")
            
            self.logger.info("TTS Weekly backup completed")
        except Exception:
            self.logger.exception("Error in TTS weekly backup")
    
    def start_scheduler(self):
        """Запуск планировщика бэкапов TTS в отдельно потоке"""
        def run_scheduler():
            while True:
                schedule.run_pending()
                time.sleep(60)  # Проверяе каждую инуту
        
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        self.logger.info("TTS Backup scheduler started")

# Глобальный экзепляр
tts_backup_manager = BackupManager("f5_tts")



