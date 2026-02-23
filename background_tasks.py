import asyncio
import logging
import time
from pathlib import Path
from file_manager import file_manager
logger = logging.getLogger(__name__)

class BackgroundTaskManager:

    def __init__(self):
        self.tasks = []
        self.running = False

    async def start(self):
        """Запуск фоновых задач"""
        if self.running:
            return
        self.running = True
        self.tasks = [asyncio.create_task(self.cleanup_files_periodically())]
        logger.info('Background tasks started')

    async def stop(self):
        """Остановка фоновых задач"""
        if not self.running:
            return
        self.running = False
        for task in self.tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.tasks = []
        logger.info('Background tasks stopped')

    async def cleanup_files_periodically(self):
        """Периодическая очистка файлов (теперь использует безопасный сервис)"""
        while self.running:
            try:
                from safe_cleanup_service import safe_cleanup_service
                cleanup_stats = safe_cleanup_service.cleanup_old_files()
                if cleanup_stats['files_deleted'] > 0:
                    mb_freed = cleanup_stats['bytes_freed'] / (1024 * 1024)
                    logger.info(f"[CLEANUP] TTS Service cleanup: {cleanup_stats['files_deleted']} files deleted, {mb_freed:.1f} MB freed")
                await asyncio.sleep(21600)
            except Exception:
                logger.exception('[ERROR] Error in TTS Service file cleanup')
                await asyncio.sleep(3600)

    async def cleanup_temp_file_delayed(self, file_path: Path, delay_seconds: int=300):
        """Удалить временный файл через указанное количество секунд"""
        await asyncio.sleep(delay_seconds)
        file_manager.cleanup_temp_file(file_path)

    async def cleanup_test_file_delayed(self, file_path: Path, delay_seconds: int=300):
        """Удалить тестовый файл через указанное количество секунд"""
        await asyncio.sleep(delay_seconds)
        file_manager.cleanup_temp_file(file_path)

    async def cleanup_production_file_delayed(self, file_path: Path, delay_seconds: int=300):
        """Удалить производственный файл через указанное количество секунд (5 минут)"""
        await asyncio.sleep(delay_seconds)
        file_manager.cleanup_temp_file(file_path)
background_task_manager = BackgroundTaskManager()
