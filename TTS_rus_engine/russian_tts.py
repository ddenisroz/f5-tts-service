"""
Мультиязычная реализация F5-TTS с поддержкой русского и английского языков
"""
import logging
import os
import re
from pathlib import Path
from typing import Optional
import tempfile
import numpy as np
import soundfile as sf
import torch
from f5_tts.api import F5TTS
from huggingface_hub import hf_hub_download
from ruaccent import RUAccent
from .yoficator_module import yoficate_text
from .number_converter import convert_numbers_in_text
from .time_converter import convert_all_time_in_text
from .date_converter import convert_all_dates_in_text
from .money_converter import convert_all_money_in_text
try:
    from ..config import config
except ImportError:
    from config import config
logger = logging.getLogger(__name__)
MODEL_ID = 'Misha24-10/F5-TTS_RUSSIAN'
CHECKPOINT = 'F5TTS_v1_Base_v2/model_last_inference.safetensors'
VOCAB = 'F5TTS_v1_Base/vocab.txt'
DEFAULT_VOICE_TRANSCRIPTION = 'Создавая уникальные цифровые объекты, вы размышляете о том насколько интересны ваши идеи миру, но задумываетель ли вы, как защитить права на свои произведения.'

class RussianTTS:

    def __init__(self, enable_accent=True, accent_model_size='turbo', ode_method='euler', use_ema=True):
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        if self.device == 'cuda':
            try:
                test_tensor = torch.zeros(1, device='cuda')
                del test_tensor
                torch.cuda.empty_cache()
                logger.info(f'CUDA проверка прошла успешно')
            except Exception:
                logger.warning('CUDA тест не прошел, переключаемся на CPU', exc_info=True)
                self.device = 'cpu'
        self.enable_accent = enable_accent
        self.accent_model_size = accent_model_size
        self.ode_method = ode_method
        self.use_ema = use_ema
        logger.info(f'F5-TTS использует устройство: {self.device}')
        self.tts_model = None
        self.accentizer = None
        try:
            self._load_models()
        except Exception:
            logger.exception('Не удалось инициализировать TTS')
            self.tts_model = None

    def is_ready(self):
        """Проверяет, готов ли TTS движок к работе."""
        return self.tts_model is not None

    def _load_models(self):
        """Загружает F5-TTS модели и RUAccent."""
        try:
            if self.enable_accent:
                logger.info(f'Загружаем RUAccent для расстановки ударений (модель: {self.accent_model_size})...')
                try:
                    self.accentizer = RUAccent()
                    self.accentizer.load(omograph_model_size=self.accent_model_size, use_dictionary=True)
                    logger.info(f'RUAccent загружен успешно (модель: {self.accent_model_size})')
                except Exception:
                    logger.warning('Не удалось загрузить RUAccent', exc_info=True)
                    self.accentizer = None
            self._load_tts_model()
            if self.tts_model is None:
                raise RuntimeError('TTS модель не загружена')
        except Exception:
            logger.exception('Text cleaned.')
            raise

    def _load_tts_model(self):
        """Загружает F5-TTS модель (поддерживает русский и английский)."""
        try:
            logger.info('Загружаем F5-TTS модель...')
            cache_dir = Path('f5_tts_cache')
            cache_dir.mkdir(exist_ok=True)
            possible_paths = [cache_dir / 'models--Misha24-10--F5-TTS_RUSSIAN' / 'snapshots' / 'main' / 'F5TTS_v1_Base_v2' / 'model_last_inference.safetensors', cache_dir / 'models--Misha24-10--F5-TTS_RUSSIAN' / 'snapshots' / '4f5ee5def0435265fe6ecf2143df2ef26d926b62' / 'F5TTS_v1_Base_v2' / 'model_last_inference.safetensors']
            local_ckpt_path = None
            for path in possible_paths:
                if path.exists():
                    local_ckpt_path = path
                    break
            if local_ckpt_path and local_ckpt_path.exists():
                logger.info(f'Text cleaned.{local_ckpt_path}')
                ckpt_path = str(local_ckpt_path)
            else:
                try:
                    ckpt_path = hf_hub_download(repo_id=MODEL_ID, filename=CHECKPOINT, cache_dir=cache_dir)
                    logger.info(f'Checkpoint скачан в: {ckpt_path}')
                except Exception as download_error:
                    logger.error(f'Ошибка загрузки модели: {download_error}')
                    logger.info('Попробуйте скачать модель вручную или проверьте интернет-соединение')
                    raise RuntimeError('Не удалось загрузить TTS модель')
            vocab_possible_paths = [cache_dir / 'models--Misha24-10--F5-TTS_RUSSIAN' / 'snapshots' / 'main' / 'vocab.txt', cache_dir / 'models--Misha24-10--F5-TTS_RUSSIAN' / 'snapshots' / '4f5ee5def0435265fe6ecf2143df2ef26d926b62' / 'F5TTS_v1_Base' / 'vocab.txt']
            local_vocab_path = None
            for path in vocab_possible_paths:
                if path.exists():
                    local_vocab_path = path
                    break
            if local_vocab_path and local_vocab_path.exists():
                logger.info(f'Text cleaned.{local_vocab_path}')
                vocab_path = str(local_vocab_path)
            else:
                try:
                    vocab_path = hf_hub_download(repo_id=MODEL_ID, filename=VOCAB, cache_dir=cache_dir)
                except Exception as vocab_error:
                    logger.error(f'Ошибка загрузки vocab: {vocab_error}')
                    logger.info('Попробуйте скачать vocab.txt вручную')
                    raise RuntimeError('Не удалось загрузить vocab файл')
            logger.info(f'Vocab.txt скачан в: {vocab_path}')
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
                import os
                os.environ['HF_HOME'] = str(cache_dir.absolute())
                os.environ['HUGGINGFACE_HUB_CACHE'] = str(cache_dir.absolute())
                os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
                os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
                os.environ['NO_PROXY'] = 'huggingface.co'
                os.environ['http_proxy'] = ''
                os.environ['https_proxy'] = ''
                os.environ['HTTP_PROXY'] = ''
                os.environ['HTTPS_PROXY'] = ''
                self.tts_model = F5TTS(model='F5TTS_v1_Base', ckpt_file=ckpt_path, vocab_file=vocab_path, ode_method=self.ode_method, use_ema=self.use_ema, device=self.device, hf_cache_dir=str(cache_dir))
                if hasattr(self.tts_model, 'model'):
                    self.tts_model.model.eval()
            except Exception as e:
                logger.exception('Ошибка инициализации F5TTS')
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.reset_peak_memory_stats()
                if 'proxy' in str(e).lower() or 'ssl' in str(e).lower():
                    logger.warning('Проблема с прокси, пробуем загрузить F5-TTS без вокодера...')
                    try:
                        self.tts_model = F5TTS(model='F5TTS_v1_Base', ckpt_file=ckpt_path, vocab_file=vocab_path, ode_method=self.ode_method, use_ema=self.use_ema, device=self.device, hf_cache_dir=str(cache_dir), vocoder=None)
                        logger.info('F5-TTS загружен без вокодера (fallback режим)')
                    except Exception:
                        logger.exception('Не удалось загрузить F5-TTS даже без вокодера')
                        raise
                else:
                    raise
            logger.info('F5-TTS модель загружена успешно.')
        except Exception:
            logger.exception('Ошибка загрузки модели')
            self.tts_model = None

    def detect_language(self, text: str) -> str:
        """Определяет язык текста."""
        cyrillic_pattern = re.compile('[а-яё]', re.IGNORECASE)
        latin_pattern = re.compile('[a-z]', re.IGNORECASE)
        cyrillic_count = len(cyrillic_pattern.findall(text))
        latin_count = len(latin_pattern.findall(text))
        logger.info(f'Анализ языка: кириллица={cyrillic_count}, латиница={latin_count}')
        if cyrillic_count > latin_count:
            logger.info(f'Выбран русский язык (кириллица > латиницы)')
            return 'russian'
        elif latin_count > cyrillic_count:
            logger.info(f'Выбран английский язык (латиница > кириллицы)')
            return 'english'
        elif cyrillic_count > 0:
            logger.info(f'Выбран русский язык (есть кириллица при равном количестве)')
            return 'russian'
        else:
            logger.info(f'Выбран русский язык (по умолчанию для чисел и символов)')
            return 'russian'

    def _is_only_symbols(self, text: str) -> bool:
        """Проверяет, состоит ли текст только из знаков препинания и символов."""
        text_no_spaces = text.replace(' ', '')
        if not text_no_spaces:
            return True
        has_letter_or_digit = any((c.isalnum() or c.isalpha() or c.isdigit() for c in text_no_spaces))
        return not has_letter_or_digit

    def _remove_long_symbol_sequences(self, text: str) -> str:
        """Удаляет последовательности из более чем 3 знаков подряд."""
        import re
        pattern = '(.)\\1{3,}'
        return re.sub(pattern, '\\1\\1\\1', text)

    def add_accents(self, text: str) -> str:
        """Добавляет ударения к русскому тексту."""
        if not self.accentizer or not text.strip():
            return text
        import re
        text = re.sub('\\s+', ' ', text.strip())
        try:
            if hasattr(self.accentizer, 'process_all'):
                accented_text = self.accentizer.process_all(text)
            elif hasattr(self.accentizer, 'process'):
                accented_text = self.accentizer.process(text)
            else:
                logger.warning('RUAccent не поддерживает доступные методы')
                return text
            logger.info(f"Добавлены ударения: '{text[:50]}...' -> '{accented_text[:50]}...'")
            return re.sub('\\s+', ' ', accented_text).strip()
        except Exception:
            logger.warning('Ошибка добавления ударений', exc_info=True)
            return text

    def preprocess_text_for_tts(self, text: str) -> str:
        """Предобработка текста с учетом языка и конвертацией чисел."""
        import re
        processed_text = re.sub('\\s+', ' ', text.strip())
        if not processed_text:
            return ''
        logger.info(f"Text cleaned.{processed_text}'")
        if self._is_only_symbols(processed_text):
            logger.warning('Сообщение состоит только из знаков - игнорируем')
            return ''
        processed_text = self._remove_long_symbol_sequences(processed_text)
        if not processed_text.strip():
            logger.warning('После удаления длинных последовательностей символов текст стал пустым')
            return ''
        language = self.detect_language(processed_text)
        logger.info(f'Определенный язык: {language}')
        processed_text = ' '.join(processed_text.split())
        if language == 'russian':
            try:
                processed_text = yoficate_text(processed_text)
                logger.info(f"После ёфикации: '{processed_text}'")
            except Exception:
                logger.warning('Ошибка ёфикации', exc_info=True)
        if language == 'russian':
            try:
                processed_text = convert_all_dates_in_text(processed_text)
                logger.info(f"После конвертации дат: '{processed_text}'")
            except Exception:
                logger.warning('Ошибка конвертации дат', exc_info=True)
        if language == 'russian':
            try:
                processed_text = convert_all_time_in_text(processed_text)
                logger.info(f"После конвертации времени: '{processed_text}'")
            except Exception:
                logger.warning('Ошибка конвертации времени', exc_info=True)
        if language == 'russian':
            try:
                processed_text = convert_all_money_in_text(processed_text)
                logger.info(f"После конвертации денежных сумм: '{processed_text}'")
            except Exception:
                logger.warning('Ошибка конвертации денежных сумм', exc_info=True)
        if language == 'russian':
            try:
                processed_text = convert_numbers_in_text(processed_text)
                logger.info(f"После конвертации чисел: '{processed_text}'")
            except Exception:
                logger.warning('Ошибка конвертации чисел', exc_info=True)
        if language == 'russian' and self.enable_accent:
            processed_text = self.add_accents(processed_text)
        elif language == 'english':
            processed_text = processed_text.strip()
            logger.info(f"Английский текст готов к синтезу: '{processed_text}'")
        if processed_text:
            processed_text = processed_text.rstrip()
            if not processed_text.endswith(('.', '!', '?')):
                processed_text += '.'
        processed_text = re.sub('\\s+', ' ', processed_text).strip()
        logger.info(f"Обработанный текст: '{processed_text}'")
        return processed_text
    SPEED_PRESETS = {'very_slow': {'name': 'Очень медленный', 'description': 'Максимально медленная речь', 'settings': {'russian': [0.1, 0.3, 0.6, 0.8, 0.9, 1.0], 'english': [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]}}, 'slow': {'name': 'Медленный', 'description': 'Замедленная речь', 'settings': {'russian': [0.3, 0.6, 0.8, 0.9, 0.9, 1.0], 'english': [0.2, 0.4, 0.5, 0.7, 0.7, 0.8]}}, 'normal': {'name': 'Нормальный', 'description': 'Обычная скорость речи', 'settings': {'russian': [0.5, 0.8, 1.0, 1.0, 1.0, 1.0], 'english': [0.3, 0.7, 0.8, 0.9, 1.0, 1.0]}}, 'fast': {'name': 'Быстрый', 'description': 'Ускоренная речь', 'settings': {'russian': [0.8, 1.0, 1.2, 1.3, 1.4, 1.5], 'english': [0.7, 1.0, 1.1, 1.2, 1.3, 1.3]}}, 'very_fast': {'name': 'Очень быстрый', 'description': 'Максимально ускоренная речь', 'settings': {'russian': [0.8, 1.1, 1.4, 1.5, 1.6, 1.8], 'english': [0.7, 1.0, 1.3, 1.5, 1.6, 1.7]}}}

    def synthesize_speech(self, text: str, ref_audio_path: str, ref_text: str='', speed: float=None, nfe_step: int=None, fix_duration: Optional[float]=None, remove_silence: bool=False, seed: Optional[int]=None, cfg_strength: float=None, target_rms: float=None, speed_preset: str='normal') -> Optional[str]:
        """Синтезирует речь с автоматическим выбором модели по языку."""
        processed_text = self.preprocess_text_for_tts(text)
        if not processed_text:
            logger.warning('Текст пустой после предобработки')
            return None
        language = self.detect_language(processed_text)
        if cfg_strength is None:
            cfg_strength = config.cfg_strength
        if target_rms is None:
            target_rms = config.target_rms
        cross_fade_duration = config.cross_fade_duration
        silence_duration_ms = config.silence_duration_ms
        sway_sampling_coef = config.sway_sampling_coef
        if speed is None:
            length_without_spaces = len(processed_text.replace(' ', ''))
            if speed_preset in self.SPEED_PRESETS:
                preset_settings = self.SPEED_PRESETS[speed_preset]['settings']
                language_key = language if language in preset_settings else 'russian'
                speed_values = preset_settings[language_key]
                if length_without_spaces <= 3:
                    speed = speed_values[0]
                elif length_without_spaces <= 8:
                    speed = speed_values[1]
                elif length_without_spaces <= 18:
                    speed = speed_values[2]
                elif length_without_spaces <= 35:
                    speed = speed_values[3]
                elif length_without_spaces <= 45:
                    speed = speed_values[4]
                else:
                    speed = speed_values[5]
                logger.info(f"Применен пресет скорости '{speed_preset}': {self.SPEED_PRESETS[speed_preset]['name']}")
                logger.info(f'Скорость для {language} (длина: {length_without_spaces}): {speed}')
            else:
                if language == 'english':
                    if length_without_spaces <= 3:
                        speed = 0.1
                    elif length_without_spaces <= 8:
                        speed = 0.2
                    elif length_without_spaces <= 18:
                        speed = 0.3
                    elif length_without_spaces <= 35:
                        speed = 0.4
                    elif length_without_spaces <= 45:
                        speed = 0.5
                    else:
                        speed = 0.6
                elif length_without_spaces <= 3:
                    speed = 0.1
                elif length_without_spaces <= 8:
                    speed = 0.3
                elif length_without_spaces <= 18:
                    speed = 0.6
                elif length_without_spaces <= 35:
                    speed = 0.8
                elif length_without_spaces <= 45:
                    speed = 0.9
                else:
                    speed = 1.0
                logger.info(f'Text cleaned.{language}: {speed}Text cleaned.{length_without_spaces})')
        if speed is not None:
            speed = max(0.1, min(2.0, speed))
        if nfe_step is None:
            length_without_spaces = len(processed_text.replace(' ', ''))
            if length_without_spaces > 120:
                nfe_step = 18
            else:
                nfe_step = 26
            logger.info(f'Автоматически определен NFE steps: {nfe_step} (длина обработанного текста: {length_without_spaces})')
        tts_model = self.tts_model
        model_name = 'F5-TTS (Russian/English)'
        if not tts_model:
            logger.error(f'Модель {model_name} не загружена')
            return None
        logger.info(f"Text cleaned.{model_name}Text cleaned.{(tts_model.device if hasattr(tts_model, 'device') else 'неизвестно')}")
        if hasattr(tts_model, 'model') and hasattr(tts_model.model, 'training'):
            logger.info(f'Text cleaned.{tts_model.model.training}')
        ref_text_to_use = ref_text
        logger.info(f"Синтезируем аудио ({model_name}): '{processed_text}' используя голос '{ref_audio_path}'")
        try:
            output_dir = config.temp_audio_path
            output_dir.mkdir(parents=True, exist_ok=True)
            import time
            timestamp = int(time.time() * 1000)
            output_filename = f'{language}_{timestamp}.wav'
            output_path = output_dir / output_filename
            infer_params = {'ref_file': ref_audio_path, 'ref_text': ref_text_to_use, 'gen_text': processed_text, 'cross_fade_duration': cross_fade_duration, 'speed': speed, 'target_rms': target_rms, 'sway_sampling_coef': sway_sampling_coef, 'cfg_strength': cfg_strength, 'nfe_step': nfe_step, 'remove_silence': remove_silence, 'seed': int(time.time() * 1000) % 2 ** 32}
            if speed is not None:
                infer_params['speed'] = float(speed)
            if fix_duration is not None:
                infer_params['fix_duration'] = fix_duration
            if seed is not None:
                infer_params['seed'] = seed
            logger.info(f'[SETTINGS] Финальные параметры синтеза:')
            logger.info(f'  - cross_fade={cross_fade_duration}, speed={speed}, silence={silence_duration_ms}ms')
            logger.info(f'  - target_rms={target_rms}, sway={sway_sampling_coef}, cfg={cfg_strength}, nfe={nfe_step}')
            logger.info(f'Text cleaned.')
            logger.info(f'  - Референсный файл: {ref_audio_path}')
            logger.info(f"  - Референсный текст: '{ref_text_to_use}'")
            logger.info(f"  - Генерируемый текст: '{processed_text}'")
            logger.info(f'  - target_rms: {target_rms}')
            logger.info(f'  - cfg_strength: {cfg_strength}')
            logger.info(f'  - sway_sampling_coef: {sway_sampling_coef}')
            logger.info(f'  - speed: {speed} (тип: {type(speed)})')
            logger.info(f'  - nfe_step: {nfe_step} (тип: {type(nfe_step)})')
            try:
                infer_params_safe = infer_params.copy()
                if 'seed' in infer_params_safe:
                    del infer_params_safe['seed']
                    logger.info('Text cleaned.')
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                (wav, sr, spect) = tts_model.infer(**infer_params_safe)
                duration_seconds = len(wav) / sr
                expected_duration = len(processed_text.split()) * 0.5
                if speed and speed != 1.0:
                    expected_duration = expected_duration / speed
                logger.info(f'Text cleaned.')
                logger.info(f'  - Длительность аудио: {duration_seconds:.2f} сек')
                logger.info(f'  - Ожидаемая длительность (speed={speed}): {expected_duration:.2f} сек')
                logger.info(f'  - Соотношение: {duration_seconds / expected_duration:.2f}x')
            except RuntimeError as cuda_error:
                if 'CUDA error' in str(cuda_error):
                    logger.error(f'CUDA ошибка при синтезе: {cuda_error}')
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        torch.cuda.synchronize()
                    logger.info('Попытка восстановления после CUDA ошибки...')
                    minimal_params = {'ref_file': ref_audio_path, 'ref_text': ref_text_to_use, 'gen_text': processed_text, 'speed': 1.0, 'nfe_step': 16}
                    (wav, sr, spect) = tts_model.infer(**minimal_params)
                else:
                    raise
            wav_rms = np.sqrt(np.mean(wav ** 2)) if len(wav) > 0 else 0
            wav_max = np.max(np.abs(wav)) if len(wav) > 0 else 0
            logger.info(f'Text cleaned.{wav_rms:.10f}, Max={wav_max:.10f}Text cleaned.{len(wav)}Text cleaned.')
            extended_silence_ms = max(silence_duration_ms, 800)
            silence_samples = int(sr * (extended_silence_ms / 1000.0))
            silence = np.zeros(silence_samples, dtype=np.float32)
            wav_padded = np.concatenate([wav, silence])
            fade_samples = int(sr * 0.3)
            if len(wav_padded) > fade_samples:
                fade = np.cos(np.linspace(0, np.pi / 2, fade_samples))
                wav_padded[-fade_samples:] *= fade
            post_fade_silence = int(sr * 0.1)
            post_silence = np.zeros(post_fade_silence, dtype=np.float32)
            wav_padded = np.concatenate([wav_padded, post_silence])
            current_rms = np.sqrt(np.mean(wav_padded ** 2))
            logger.info(f'Text cleaned.{current_rms:.10f}, Max аплитуда: {np.max(np.abs(wav_padded)):.10f}')
            if current_rms == 0:
                logger.error('Text cleaned.')
            sf.write(str(output_path), wav_padded, sr)
            logger.info(f'Аудио синтезировано и сохранено в {output_path} (модель: {model_name})')
            return str(output_path.resolve())
        except Exception:
            logger.exception('Ошибка при синтезе')
            return None

    def apply_volume_to_audio(self, audio_path: str, volume_level: float) -> bool:
        """
        Применяет громкость к уже сгенерированному аудио файлу.
        
        Args:
            audio_path: Путь к аудио файлу
            volume_level: Уровень громкости (0.0 - 1.0, где 0.5 = 50%)
        
        Returns:
            bool: True если успешно, False если ошибка
        """
        try:
            if not os.path.exists(audio_path):
                logger.error(f'Audio file not found: {audio_path}')
                return False
            (audio_data, sample_rate) = sf.read(audio_path)
            volume_multiplier = volume_level / 50.0
            audio_data_modified = audio_data * volume_multiplier
            audio_data_modified = np.clip(audio_data_modified, -1.0, 1.0)
            sf.write(audio_path, audio_data_modified, sample_rate)
            logger.info(f'Volume applied to audio: {audio_path}, level: {volume_level}%, multiplier: {volume_multiplier:.2f}x')
            return True
        except Exception:
            logger.exception('Error applying volume to audio {audio_path}')
            return False

    async def synthesize(self, text: str, voice_name: str, output_path: str, volume_level: float=50.0, **kwargs) -> bool:
        """Text cleaned."""
        try:
            voice_audio_path = self._get_voice_audio_path(voice_name)
            if not voice_audio_path:
                logger.error(f'Voice audio not found for voice: {voice_name}')
                return False
            logger.info(f'[FIX] Synthesize called with kwargs: {kwargs}')
            result_path = self.synthesize_speech(text=text, ref_audio_path=voice_audio_path, ref_text='' ** kwargs)
            if not result_path or not os.path.exists(result_path):
                logger.error(f'Synthesis failed or output file not created: {result_path}')
                return False
            if result_path != output_path:
                import shutil
                shutil.copy2(result_path, output_path)
                try:
                    os.remove(result_path)
                except OSError:
                    pass
            if volume_level != 50.0:
                volume_applied = self.apply_volume_to_audio(output_path, volume_level)
                if not volume_applied:
                    logger.warning(f'Failed to apply volume to {output_path}, but synthesis succeeded')
            return True
        except Exception:
            logger.exception('Error in synthesize method')
            return False

    def _get_voice_audio_path(self, voice_name: str) -> str:
        """Text cleaned."""
        try:
            from database import get_db, Voice as VoiceModel
            db = next(get_db())
            try:
                voice = db.query(VoiceModel).filter(VoiceModel.name == voice_name).first()
                if voice and voice.file_path:
                    voice_path = Path(voice.file_path)
                    if voice_path.exists():
                        return str(voice_path)
                    else:
                        logger.warning(f'Voice file path exists in DB but file not found: {voice.file_path}')
            finally:
                db.close()
            from config import config
            voices_dir = config.voices_path
            voice_file = voices_dir / f'{voice_name}.wav'
            if voice_file.exists():
                return str(voice_file)
            for ext in ['.wav', '.mp3', '.flac']:
                voice_file = voices_dir / f'{voice_name}{ext}'
                if voice_file.exists():
                    return str(voice_file)
            logger.warning(f'Voice audio file not found for: {voice_name}')
            return None
        except Exception:
            logger.exception('Error getting voice audio path for {voice_name}')
            return None
if __name__ == '__main__':
    tts = RussianTTS()
    if tts.russian_tts:
        logger.info('Russian TTS model loaded successfully')
    else:
        logger.error('Failed to load TTS models')
