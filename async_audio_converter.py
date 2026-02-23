#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Async Audio Converter for F5-TTS requirements
Asynchronous version of audio converter with worker pool
"""

import asyncio
import logging
import os
import uuid
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor
import soundfile as sf
import numpy as np
import librosa

logger = logging.getLogger(__name__)

# F5-TTS requirements
TARGET_SAMPLE_RATE = 48000  # 48kHz для максимального качества
TARGET_CHANNELS = 1  # Mono
TARGET_BIT_DEPTH = 16  # 16-bit
TARGET_DURATION_MIN = 3.0  # Minimum 3 seconds
TARGET_DURATION_MAX = 10.0  # Maximum 10 seconds

class AsyncAudioConverter:
    """
    Асинхронный конвертер аудио для F5-TTS
    """
    
    def __init__(self, max_workers: int = 2):
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._running = False
        self._conversion_tasks: Dict[str, Dict[str, Any]] = {}
        
    async def start_workers(self):
        """Запуск воркеров"""
        if self._running:
            return
            
        self._running = True
        logger.info(f"Async Audio Converter started with {self.max_workers} workers")
        
    async def stop_workers(self):
        """Остановка воркеров"""
        if not self._running:
            return
            
        self._running = False
        self.executor.shutdown(wait=True)
        logger.info("Async Audio Converter stopped")
        
    async def convert_audio_async(self, input_path: str, output_path: str) -> str:
        """
        Асинхронная конвертация аудио
        
        Args:
            input_path: Путь к входному файлу
            output_path: Путь к выходному файлу
            
        Returns:
            str: ID задачи конвертации
        """
        task_id = str(uuid.uuid4())
        
        # Сохраняем информацию о задаче
        self._conversion_tasks[task_id] = {
            'input_path': input_path,
            'output_path': output_path,
            'status': 'pending',
            'result': None,
            'error': None
        }
        
        # Запускаем конвертацию в отдельном потоке
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(
            self.executor,
            self._convert_audio_sync,
            input_path,
            output_path,
            task_id
        )
        
        # Не ждем завершения, возвращаем ID задачи
        asyncio.create_task(self._handle_conversion_result(future, task_id))
        
        return task_id
        
    def _convert_audio_sync(self, input_path: str, output_path: str, task_id: str) -> bool:
        """
        Синхронная конвертация аудио (выполняется в отдельном потоке)
        """
        try:
            logger.info(f"Converting audio: {input_path} -> {output_path}")
            
            # Check if input file exists and has content
            if not os.path.exists(input_path):
                raise FileNotFoundError(f"Input file not found: {input_path}")
            
            if os.path.getsize(input_path) == 0:
                raise ValueError("Input file is empty")
            
            # Load audio file
            audio_data, sample_rate = librosa.load(input_path, sr=None, mono=False)
            
            # Convert to mono if stereo
            if len(audio_data.shape) > 1:
                audio_data = librosa.to_mono(audio_data)
            
            # Resample to target sample rate
            if sample_rate != TARGET_SAMPLE_RATE:
                audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=TARGET_SAMPLE_RATE)
            
            # Check duration
            duration = len(audio_data) / TARGET_SAMPLE_RATE
            if duration < TARGET_DURATION_MIN:
                raise ValueError(f"Audio too short: {duration:.2f}s (minimum: {TARGET_DURATION_MIN}s)")
            
            if duration > TARGET_DURATION_MAX:
                # Trim to maximum duration
                max_samples = int(TARGET_DURATION_MAX * TARGET_SAMPLE_RATE)
                audio_data = audio_data[:max_samples]
                logger.warning(f"Audio trimmed to {TARGET_DURATION_MAX}s")
            
            # Normalize audio
            audio_data = librosa.util.normalize(audio_data)
            
            # Convert to 16-bit PCM
            audio_data = (audio_data * 32767).astype(np.int16)
            
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Save as WAV
            sf.write(output_path, audio_data, TARGET_SAMPLE_RATE, subtype='PCM_16')
            
            logger.info(f"Audio conversion successful: {output_path}")
            return True
            
        except Exception:
            logger.exception("Audio conversion failed")
            return False
            
    async def _handle_conversion_result(self, future, task_id: str):
        """Обработка результата конвертации"""
        try:
            result = await future
            self._conversion_tasks[task_id]['status'] = 'completed' if result else 'failed'
            self._conversion_tasks[task_id]['result'] = result
        except Exception as e:
            self._conversion_tasks[task_id]['status'] = 'failed'
            self._conversion_tasks[task_id]['error'] = str(e)
            logger.exception("Conversion task {task_id} failed")
            
    async def get_conversion_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Получить результат конвертации
        
        Args:
            task_id: ID задачи
            
        Returns:
            Dict с результатом или None если задача не найдена
        """
        if task_id not in self._conversion_tasks:
            return None
            
        task = self._conversion_tasks[task_id]
        
        if task['status'] == 'completed':
            return {
                'success': True,
                'output_path': task['output_path'],
                'task_id': task_id
            }
        elif task['status'] == 'failed':
            return {
                'success': False,
                'error': task['error'],
                'task_id': task_id
            }
        else:
            return {
                'success': False,
                'status': 'pending',
                'task_id': task_id
            }
            
    def validate_audio_for_f5tts(self, file_path: str) -> bool:
        """
        Проверить, подходит ли аудио файл для F5-TTS
        
        Args:
            file_path: Путь к аудио файлу
            
        Returns:
            bool: True если файл подходит
        """
        try:
            if not os.path.exists(file_path):
                return False
                
            if os.path.getsize(file_path) == 0:
                return False
                
            # Load audio to check basic properties
            audio_data, sample_rate = librosa.load(file_path, sr=None, mono=False)
            
            # Check if mono
            if len(audio_data.shape) > 1:
                audio_data = librosa.to_mono(audio_data)
            
            # Check duration
            duration = len(audio_data) / sample_rate
            if duration < TARGET_DURATION_MIN or duration > TARGET_DURATION_MAX:
                return False
                
            return True
            
        except Exception:
            logger.exception("Audio validation failed")
            return False

# Глобальный экземпляр
async_audio_converter = AsyncAudioConverter(max_workers=2)

