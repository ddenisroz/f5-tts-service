import logging
import asyncio
from pathlib import Path
from TTS_rus_engine.russian_tts import RussianTTS
from config import config
logger = logging.getLogger(__name__)

class TTSEngineManager:

    def __init__(self):
        self.tts_engine = None
        self.transcriber = None
        self.is_initialized = False

    async def initialize(self):
        """Text cleaned."""
        try:
            logger.info('Initializing AI TTS engine (F5-TTS)...')
            self.tts_engine = RussianTTS()
            import os
            if os.getenv('DISABLE_TRANSCRIPTION', 'false').lower() == 'true':
                logger.info('Transcription disabled via DISABLE_TRANSCRIPTION env variable')
                self.transcriber = None
            else:
                try:
                    from faster_whisper import WhisperModel
                    cache_dir = Path(__file__).parent / 'f5_tts_cache'
                    cache_dir.mkdir(exist_ok=True)
                    try:
                        self.transcriber = WhisperModel('turbo', device='auto', compute_type='auto', download_root=str(cache_dir), local_files_only=True)
                        logger.info('Faster-Whisper turbo transcriber loaded from cache')
                    except Exception as cache_error:
                        logger.info(f'Turbo model not in cache, downloading: {cache_error}')
                        self.transcriber = WhisperModel('turbo', device='auto', compute_type='auto', download_root=str(cache_dir))
                        logger.info('Faster-Whisper turbo transcriber downloaded and loaded')
                except Exception:
                    logger.warning('Failed to load Faster-Whisper turbo model, trying base', exc_info=True)
                    try:
                        cache_dir = Path(__file__).parent / 'f5_tts_cache'
                        cache_dir.mkdir(exist_ok=True)
                        try:
                            self.transcriber = WhisperModel('base', device='auto', compute_type='auto', download_root=str(cache_dir), local_files_only=True)
                            logger.info('Faster-Whisper base transcriber loaded from cache')
                        except Exception as cache_error:
                            self.transcriber = WhisperModel('base', device='auto', compute_type='auto', download_root=str(cache_dir))
                            logger.info('Faster-Whisper base transcriber downloaded and loaded')
                    except Exception:
                        logger.warning('Failed to load Faster-Whisper, disabling transcription', exc_info=True)
                        self.transcriber = None
                        logger.info('TTS will work without transcription support')
            self.is_initialized = True
            logger.info('TTS engine initialized successfully')
        except Exception:
            logger.exception('Failed to initialize TTS engine')
            self.is_initialized = False
            raise

    async def shutdown(self):
        """Завершение работы TTS движка"""
        try:
            if self.tts_engine:
                if hasattr(self.tts_engine, 'cleanup'):
                    await self.tts_engine.cleanup()
                else:
                    logger.info('TTS engine does not have cleanup method, skipping')
                self.tts_engine = None
            self.transcriber = None
            self.is_initialized = False
            logger.info('TTS engine shutdown completed')
        except Exception:
            logger.exception('Error during TTS engine shutdown')

    def is_ready(self) -> bool:
        """Проверка готовности движка"""
        if not self.is_initialized or self.tts_engine is None:
            return False
        if hasattr(self.tts_engine, 'is_ready'):
            return self.tts_engine.is_ready()
        else:
            return True

    async def synthesize(self, text: str, voice_name: str, output_path: str, **kwargs) -> bool:
        """Синтез речи"""
        if not self.is_ready():
            raise RuntimeError('TTS engine not initialized')
        try:
            return await self.tts_engine.synthesize(text, voice_name, output_path, **kwargs)
        except Exception:
            logger.exception('Error during synthesis')
            raise

    async def synthesize_speech_async(self, text: str, voice: str='female_1', user_id: int=None, channel_name: str=None, author: str=None, word_filter: list=None, blocked_users: list=None, volume: float=50.0, tts_settings: dict=None) -> dict:
        """Text cleaned."""
        if not self.is_ready():
            return {'success': False, 'error': 'TTS engine not initialized'}
        try:
            logger.info(f"[MIC] Synthesizing for {channel_name} | {author}: '{text[:50]}...'")
            from database import SessionLocal, Voice as VoiceModel
            db = SessionLocal()
            try:
                voice_record = db.query(VoiceModel).filter(VoiceModel.name == voice).first()
                if not voice_record:
                    logger.warning(f"Voice '{voice}' not found in DB, trying fallback options")
                    voice_record = db.query(VoiceModel).filter(VoiceModel.name == 'female_1').first()
                    if not voice_record:
                        voice_record = db.query(VoiceModel).filter(VoiceModel.voice_type == 'global').first()
                        if voice_record:
                            logger.info(f'Using first available global voice: {voice_record.name}')
                        else:
                            voice_record = db.query(VoiceModel).first()
                            if voice_record:
                                logger.info(f'Using first available voice: {voice_record.name}')
                            else:
                                logger.error('No voices found in database')
                                return {'success': False, 'error': 'No voices available'}
                ref_audio_path = voice_record.file_path
                ref_text = voice_record.reference_text or ''
                if tts_settings and isinstance(tts_settings, dict):
                    voice_settings_raw = tts_settings.get('voice_settings')
                    voice_settings = voice_settings_raw if isinstance(voice_settings_raw, dict) else {}
                else:
                    voice_settings = {}
                DEFAULT_CFG_STRENGTH = config.cfg_strength
                DEFAULT_SPEED_PRESET = 'normal'
                cfg_strength = voice_settings.get('cfg_strength')
                if cfg_strength is None:
                    cfg_strength = voice_record.cfg_strength or DEFAULT_CFG_STRENGTH
                    logger.debug(f"[SETTINGS] Using default cfg_strength from Voice '{voice_record.name}': {cfg_strength} (config default: {DEFAULT_CFG_STRENGTH})")
                else:
                    logger.debug(f'[SETTINGS] Using personal cfg_strength: {cfg_strength} (default from Voice: {voice_record.cfg_strength})')
                speed_preset = voice_settings.get('speed_preset')
                if speed_preset is None:
                    speed_preset = voice_record.speed_preset or DEFAULT_SPEED_PRESET
                    logger.debug(f"[SETTINGS] Using default speed_preset from Voice '{voice_record.name}': {speed_preset} (config default: {DEFAULT_SPEED_PRESET})")
                else:
                    logger.debug(f'[SETTINGS] Using personal speed_preset: {speed_preset} (default from Voice: {voice_record.speed_preset})')
                if voice_settings:
                    logger.info(f'[SETTINGS] Final voice settings: cfg={cfg_strength}, speed={speed_preset}, volume={volume}% (personal settings applied)')
                else:
                    logger.info(f"[SETTINGS] Using default voice settings from Voice '{voice_record.name}': cfg={cfg_strength}, speed={speed_preset}, volume={volume}% (admin defaults)")
            finally:
                db.close()
            loop = asyncio.get_event_loop()
            audio_path = await loop.run_in_executor(None, self.tts_engine.synthesize_speech, text, ref_audio_path, ref_text, None, None, None, False, None, cfg_strength, None, speed_preset)
            if audio_path and Path(audio_path).exists():
                logger.info(f'[OK] Speech synthesized: {audio_path}')
                audio_path_obj = Path(audio_path).resolve()
                abs_audio_path = config.audio_path.resolve()
                try:
                    relative_path = audio_path_obj.relative_to(abs_audio_path)
                    audio_url = f'/audio/{relative_path.as_posix()}'
                except ValueError:
                    audio_url = f'/audio/{audio_path_obj.name}'
                return {'success': True, 'audio_url': audio_url, 'audio_path': str(audio_path), 'voice': voice, 'duration': 0, 'tts_type': 'f5'}
            else:
                logger.error('[ERROR] TTS synthesis failed: no audio file generated')
                return {'success': False, 'error': 'No audio file generated'}
        except Exception:
            logger.exception('[ERROR] TTS synthesis error')
            return {'success': False, 'error': 'Synthesis failed'}

    async def synthesize_with_conversion_async(self, text: str, voice: str='female_1', user_id: int=None, target_format: str='wav', target_sample_rate: int=22050) -> str:
        """
        Асинхронный синтез с конвертацией аудио
        
        Args:
            text: Текст для озвучивания
            voice: Голос для синтеза
            user_id: ID пользователя
            target_format: Целевой формат аудио
            target_sample_rate: Целевая частота дискретизации
            
        Returns:
            str: Путь к сгенерированному и сконвертированному аудио файлу
        """
        try:
            from async_tts_engine import async_tts_engine
            from async_audio_converter import async_audio_converter
            synthesis_task_id = await async_tts_engine.synthesize_speech_async(text=text, voice=voice, user_id=user_id)
            synthesis_result = None
            max_wait_time = 30
            wait_time = 0
            while wait_time < max_wait_time:
                synthesis_result = await async_tts_engine.get_task_result(synthesis_task_id)
                if synthesis_result:
                    break
                await asyncio.sleep(0.5)
                wait_time += 0.5
            if not synthesis_result:
                logger.error('Synthesis task did not complete in time')
                return None
            original_path = Path(synthesis_result)
            converted_path = original_path.parent / f'{original_path.stem}_converted.{target_format}'
            conversion_task_id = await async_audio_converter.convert_audio_async(input_path=str(original_path), output_path=str(converted_path), target_format=target_format, target_sample_rate=target_sample_rate)
            conversion_result = None
            wait_time = 0
            while wait_time < max_wait_time:
                conversion_result = await async_audio_converter.get_conversion_result(conversion_task_id)
                if conversion_result:
                    break
                await asyncio.sleep(0.5)
                wait_time += 0.5
            if not conversion_result:
                logger.error('Audio conversion task did not complete in time')
                return synthesis_result
            try:
                if original_path.exists():
                    original_path.unlink()
                    logger.info(f'Removed original file after conversion: {original_path}')
            except Exception:
                logger.warning('Failed to remove original file', exc_info=True)
            logger.info(f'Speech synthesized and converted successfully: {conversion_result}')
            return conversion_result
        except Exception:
            logger.exception('Async synthesis with conversion error')
            return None

    def transcribe(self, audio_path: str) -> str:
        """Транскрипция аудио с оптимизацией для русского языка"""
        if not self.transcriber:
            raise RuntimeError('Transcriber not available')
        try:
            if hasattr(self.transcriber, 'transcribe') and hasattr(self.transcriber.transcribe, '__call__'):
                (segments, info) = self.transcriber.transcribe(audio_path, language='ru', task='transcribe', beam_size=5, best_of=5, patience=1, length_penalty=1, temperature=0.0, compression_ratio_threshold=2.4, log_prob_threshold=-1.0, no_speech_threshold=0.6, condition_on_previous_text=True, prompt_reset_on_temperature=0.5, initial_prompt=None, prefix=None, suppress_blank=True, suppress_tokens=[-1], without_timestamps=True, max_initial_timestamp=0.0, word_timestamps=False, vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500))
                text_parts = []
                for segment in segments:
                    text_parts.append(segment.text.strip())
                text = ' '.join(text_parts)
            else:
                result = self.transcriber.transcribe(audio_path, language='ru', task='transcribe', fp16=False, verbose=False)
                text = result['text'].strip()
            text = ' '.join(text.split())
            logger.info(f'Transcription completed: {len(text)} characters')
            return text
        except Exception:
            logger.exception('Error during transcription')
            raise
tts_engine_manager = TTSEngineManager()
