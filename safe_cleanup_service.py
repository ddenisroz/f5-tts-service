# F5_tts/safe_cleanup_service.py
"""
езопасный сервис очистки файлов
Удаляет только вреенные файлы, НЕ ТРОГАЕТ файлы голосов
"""
import os
import time
import logging
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class SafeCleanupService:
    """
    езопасный сервис очистки файлов
    
    Удаляет ТОЛЬКО:
    - Вреенные файлы F5-TTS (temp/)
    - Тестовые файлы F5-TTS (test/)  
    - Файлы gTTS (basic_tts_*.wav)
    
    НЕ ТРОГАЕТ:
    - Файлы голосов (voices/)
    - Любые файлы в папках голосов
    """
    
    def __init__(self):
        self.max_age_hours = 6  # Удалять файлы старше 6 часов
        self.max_age_seconds = self.max_age_hours * 3600
        
        # езопасные папки для очистки (НЕ голоса!)
        self.safe_cleanup_paths = []
        
        # Папки голосов (НЕ ТРОГАТЬ!)
        self.voice_paths = []
        
        self._setup_paths()
    
    def _setup_paths(self):
        """Настройка путей для безопасной очистки"""
        try:
            from config import config
            
            # ЕЗОПАСНЫЕ папки для очистки
            self.safe_cleanup_paths = [
                config.temp_audio_path,      # F5_tts/audio/temp/
                config.test_audio_path,      # F5_tts/audio/test/
            ]
            
            # ПАПК ГОЛОСОВ - НЕ ТРОГАТЬ!
            self.voice_paths = [
                config.voices_path,          # F5_tts/audio/voices/
                config.global_voices_path,   # F5_tts/audio/voices/global/
                config.user_voices_path,     # F5_tts/audio/voices/user/
            ]
            
            # Добавляе папку gTTS из external service (disabled)
                
            logger.info(f"[OK] Safe cleanup paths configured:")
            logger.info(f"  Safe to clean: {[str(p) for p in self.safe_cleanup_paths]}")
            logger.info(f"  Voice paths (protected): {[str(p) for p in self.voice_paths]}")
            
        except Exception:
            logger.exception("[ERROR] Error setting up cleanup paths")
    
    def is_voice_file(self, file_path: Path) -> bool:
        """Проверяет, является ли файл файло голоса (НЕ УДАЛЯТЬ!)"""
        try:
            # Проверяе, находится ли файл в папке голосов
            for voice_path in self.voice_paths:
                if voice_path.exists() and file_path.is_relative_to(voice_path):
                    return True
            
            # Дополнительная проверка по иени файла
            filename = file_path.name.lower()
            if any(keyword in filename for keyword in ['voice', 'ref', 'reference', 'sample']):
                return True
                
            return False
            
        except Exception:
            logger.exception("Error checking if file is voice")
            return True  # В случае сонений - НЕ удаляе!
    
    def cleanup_old_files(self) -> Dict[str, Any]:
        """
        езопасная очистка старых файлов
        
        Returns:
            Статистика очистки
        """
        cleanup_stats = {
            'files_deleted': 0,
            'bytes_freed': 0,
            'errors': 0,
            'voice_files_protected': 0,
            'cleanup_time': datetime.now().isoformat()
        }
        
        current_time = time.time()
        
        for cleanup_path in self.safe_cleanup_paths:
            if not cleanup_path.exists():
                continue
                
            try:
                logger.info(f"[CLEANUP] Cleaning up: {cleanup_path}")
                
                for file_path in cleanup_path.rglob("*"):
                    if not file_path.is_file():
                        continue
                    
                    # Проверяе, что это НЕ файл голоса
                    if self.is_voice_file(file_path):
                        cleanup_stats['voice_files_protected'] += 1
                        logger.debug(f"[SHIELD] Protected voice file: {file_path}")
                        continue
                    
                    # Проверяе расширение файла
                    if file_path.suffix.lower() not in ['.wav', '.mp3', '.m4a', '.aac']:
                        continue
                    
                    # Проверяе возраст файла
                    try:
                        file_age = current_time - file_path.stat().st_mtime
                        if file_age > self.max_age_seconds:
                            # езопасно удаляе файл
                            file_size = file_path.stat().st_size
                            file_path.unlink()
                            
                            cleanup_stats['files_deleted'] += 1
                            cleanup_stats['bytes_freed'] += file_size
                            
                            logger.info(f"[DELETE] Deleted: {file_path} (age: {file_age/3600:.1f}h)")
                            
                    except Exception:
                        cleanup_stats['errors'] += 1
                        logger.exception("[ERROR] Error deleting {file_path}")
                        
            except Exception:
                cleanup_stats['errors'] += 1
                logger.exception("[ERROR] Error cleaning {cleanup_path}")
        
        # Логируе результаты
        if cleanup_stats['files_deleted'] > 0:
            mb_freed = cleanup_stats['bytes_freed'] / (1024 * 1024)
            logger.info(f"[OK] Cleanup completed: {cleanup_stats['files_deleted']} files deleted, {mb_freed:.1f} MB freed")
        
        if cleanup_stats['voice_files_protected'] > 0:
            logger.info(f"[SHIELD] Protected {cleanup_stats['voice_files_protected']} voice files")
            
        if cleanup_stats['errors'] > 0:
            logger.warning(f"[WARN] {cleanup_stats['errors']} errors during cleanup")
        
        return cleanup_stats
    
    def get_cleanup_stats(self) -> Dict[str, Any]:
        """Получить статистику файлов для очистки"""
        stats = {
            'total_files': 0,
            'files_to_clean': 0,
            'voice_files': 0,
            'total_size_bytes': 0,
            'size_to_clean_bytes': 0,
            'oldest_file_age_hours': 0,
            'cleanup_paths': [str(p) for p in self.safe_cleanup_paths],
            'voice_paths': [str(p) for p in self.voice_paths]
        }
        
        current_time = time.time()
        oldest_age = 0
        
        for cleanup_path in self.safe_cleanup_paths:
            if not cleanup_path.exists():
                continue
                
            for file_path in cleanup_path.rglob("*"):
                if not file_path.is_file():
                    continue
                
                if file_path.suffix.lower() not in ['.wav', '.mp3', '.m4a', '.aac']:
                    continue
                
                try:
                    file_size = file_path.stat().st_size
                    file_age = current_time - file_path.stat().st_mtime
                    file_age_hours = file_age / 3600
                    
                    stats['total_files'] += 1
                    stats['total_size_bytes'] += file_size
                    
                    if self.is_voice_file(file_path):
                        stats['voice_files'] += 1
                    elif file_age > self.max_age_seconds:
                        stats['files_to_clean'] += 1
                        stats['size_to_clean_bytes'] += file_size
                    
                    oldest_age = max(oldest_age, file_age_hours)
                    
                except Exception:
                    logger.exception("Error getting stats for %s", file_path)
        
        stats['oldest_file_age_hours'] = oldest_age
        stats['total_size_mb'] = stats['total_size_bytes'] / (1024 * 1024)
        stats['size_to_clean_mb'] = stats['size_to_clean_bytes'] / (1024 * 1024)
        
        return stats

# Глобальный экзепляр
safe_cleanup_service = SafeCleanupService()





