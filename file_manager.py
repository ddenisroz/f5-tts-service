import os
import time
import shutil
import tempfile
import logging
from pathlib import Path
from typing import Optional, List
from audio_converter import convert_audio_for_f5tts, validate_audio_for_f5tts
logger = logging.getLogger(__name__)

class FileManager:

    def __init__(self):
        self.base_path = Path(__file__).parent
        from config import config
        self.voices_path = config.voices_path
        self.temp_path = config.temp_audio_path
        self.test_path = config.test_audio_path
        self.voices_path.mkdir(exist_ok=True)
        self.temp_path.mkdir(exist_ok=True)
        self.test_path.mkdir(exist_ok=True)

    def get_voice_file_path(self, voice_name: str) -> Optional[Path]:
        """Получить путь к файлу голоса"""
        search_paths = [self.voices_path / 'user' / voice_name, self.voices_path / 'global' / voice_name, self.voices_path / voice_name]
        for path in search_paths:
            if path.is_file():
                return path
            for ext in ['.wav', '.mp3', '.m4a', '.aac']:
                file_path = path.with_suffix(ext)
                if file_path.is_file():
                    return file_path
        return None

    def delete_voice_file(self, voice_name: str) -> bool:
        """Удалить файл голоса"""
        file_path = self.get_voice_file_path(voice_name)
        if file_path and file_path.exists():
            try:
                file_path.unlink()
                logger.info(f'Deleted voice file: {file_path}')
                return True
            except Exception:
                logger.exception('Error deleting voice file {file_path}')
                return False
        return False

    def save_uploaded_file(self, file, voice_name: str, user_id: Optional[str]=None) -> Optional[Path]:
        """Сохранить загруженный файл"""
        try:
            from config import config
            if user_id:
                save_dir = config.user_voices_path / str(user_id)
            else:
                save_dir = config.global_voices_path
            save_dir.mkdir(parents=True, exist_ok=True)
            temp_path = config.temp_audio_path / f'temp_{voice_name}_{file.filename}'
            with open(temp_path, 'wb') as buffer:
                shutil.copyfileobj(file.file, buffer)
            output_path = save_dir / f'{voice_name}.wav'
            success = convert_audio_for_f5tts(str(temp_path), str(output_path))
            temp_path.unlink()
            if success:
                logger.info(f'Voice file saved: {output_path}')
                return output_path
            else:
                logger.error(f'Failed to convert voice file: {voice_name}')
                return None
        except Exception:
            logger.exception('Error saving voice file {voice_name}')
            return None

    def cleanup_temp_file(self, file_path: Path):
        """Удалить временный файл"""
        try:
            if file_path.exists():
                file_path.unlink()
                logger.info(f'Cleaned up temp file: {file_path}')
        except Exception:
            logger.exception('Error cleaning up temp file {file_path}')

    def cleanup_old_files(self, max_age_hours: int=24):
        """Очистить старые файлы"""
        try:
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            for directory in [self.temp_path, self.test_path]:
                if not directory.exists():
                    continue
                for file_path in directory.iterdir():
                    if file_path.is_file():
                        file_age = current_time - file_path.stat().st_mtime
                        if file_age > max_age_seconds:
                            file_path.unlink()
                            logger.info(f'Cleaned up old file: {file_path}')
        except Exception:
            logger.exception('Error during cleanup')

    def get_file_size(self, file_path: Path) -> int:
        """Получить размер файла"""
        try:
            return file_path.stat().st_size
        except Exception:
            return 0

    def validate_audio_file(self, file_path: str) -> bool:
        """Проверить валидность аудиофайла"""
        try:
            return validate_audio_for_f5tts(file_path)
        except Exception:
            logger.exception('Error validating audio file {file_path}')
            return False

    def list_voice_files(self, user_id: Optional[str]=None) -> List[Path]:
        """Получить список файлов голосов"""
        files = []
        if user_id:
            user_dir = self.voices_path / 'user' / user_id
            if user_dir.exists():
                files.extend(user_dir.glob('*.wav'))
        else:
            global_dir = self.voices_path / 'global'
            if global_dir.exists():
                files.extend(global_dir.glob('*.wav'))
        return files
file_manager = FileManager()
