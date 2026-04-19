from __future__ import annotations

import asyncio
import importlib
import io
import logging
import os
import re
import shutil
import sys
import tempfile
import types
from collections.abc import Iterable, Iterator
from pathlib import Path
from time import perf_counter
from typing import Any

from ..audio_processing import convert_audio_to_wav
from ..logging_utils import get_request_logger, merge_request_context
from .base import BaseTtsEngine, SynthesisResult

logger = logging.getLogger(__name__)
TRAINER_MODULE_NAME = "f5_tts.model.trainer"

CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
LATIN_RE = re.compile(r"[A-Za-z]")
LEGACY_SPEED_PRESETS: dict[str, dict[str, list[float]]] = {
    "very_slow": {
        "russian": [0.1, 0.3, 0.6, 0.8, 0.9, 1.0],
        "english": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
    },
    "slow": {
        "russian": [0.3, 0.6, 0.8, 0.9, 0.9, 1.0],
        "english": [0.2, 0.4, 0.5, 0.7, 0.7, 0.8],
    },
    "normal": {
        "russian": [0.5, 0.8, 1.0, 1.0, 1.0, 1.0],
        "english": [0.3, 0.7, 0.8, 0.9, 1.0, 1.0],
    },
    "fast": {
        "russian": [0.8, 1.0, 1.2, 1.3, 1.4, 1.5],
        "english": [0.7, 1.0, 1.1, 1.2, 1.3, 1.3],
    },
    "very_fast": {
        "russian": [0.8, 1.1, 1.4, 1.5, 1.6, 1.8],
        "english": [0.7, 1.0, 1.3, 1.5, 1.6, 1.7],
    },
}
LEGACY_TEXT_LENGTH_BUCKETS = (3, 8, 18, 35, 45)
LEGACY_SHORT_TEXT_NFE_STEP = 26
LEGACY_LONG_TEXT_NFE_STEP = 18
LEGACY_LONG_TEXT_THRESHOLD = 120
LEGACY_FALLBACK_NFE_STEP = 16
LEGACY_FALLBACK_SPEED = 1.0
LEGACY_MIN_TAIL_SILENCE_MS = 800
LEGACY_FADE_OUT_SEC = 0.3
LEGACY_POST_FADE_SILENCE_SEC = 0.1
REFERENCE_AUDIO_SAMPLE_RATE = 24000


class _LoggingProgress:
    def __init__(self, request_logger) -> None:
        self._logger = request_logger

    def tqdm(self, iterable: Iterable[Any], desc: str | None = None, total: int | None = None) -> Iterator[Any]:
        return _LoggingProgressIterator(self._logger, iterable, desc=desc, total=total)


class _LoggingProgressIterator:
    def __init__(self, request_logger, iterable: Iterable[Any], *, desc: str | None, total: int | None) -> None:
        self._logger = request_logger
        self._iterable = iterable
        self._desc = desc or "inference"
        self._total = total if total is not None else self._guess_total(iterable)

    def __iter__(self) -> Iterator[Any]:
        self._logger.info("Inference progress started desc=%s total=%s", self._desc, self._total)
        for index, item in enumerate(self._iterable, start=1):
            self._logger.info("Inference progress desc=%s step=%s total=%s", self._desc, index, self._total)
            yield item
        self._logger.info("Inference progress completed desc=%s total=%s", self._desc, self._total)

    @staticmethod
    def _guess_total(iterable: Iterable[Any]) -> int | None:
        try:
            return len(iterable)  # type: ignore[arg-type]
        except Exception:
            return None


class F5Engine(BaseTtsEngine):
    def __init__(
        self,
        *,
        mode: str,
        upstream_dir: Path,
        russian_weights_dir: Path,
        model_name: str,
        checkpoint_file: str,
        vocab_file: str,
        hf_cache_dir: Path,
        vocoder_local_dir: Path,
        vocoder_repo_id: str,
        device: str,
        ode_method: str,
        use_ema: bool,
        target_rms: float,
        cross_fade_duration: float,
        nfe_step: int,
        sway_sampling_coef: float,
        default_cfg_strength: float,
        default_speed_preset: str,
    ) -> None:
        self.mode = mode.strip().lower()
        self.upstream_dir = upstream_dir
        self.russian_weights_dir = russian_weights_dir
        self.model_name = model_name
        self.checkpoint_file = checkpoint_file.strip()
        self.vocab_file = vocab_file.strip()
        self.hf_cache_dir = hf_cache_dir
        self.vocoder_local_dir = vocoder_local_dir
        self.vocoder_repo_id = vocoder_repo_id.strip() or "charactr/vocos-mel-24khz"
        self.device = (device or "").strip()
        self.ode_method = ode_method
        self.use_ema = bool(use_ema)
        self.target_rms = float(target_rms)
        self.cross_fade_duration = float(cross_fade_duration)
        self.nfe_step = int(nfe_step)
        self.sway_sampling_coef = float(sway_sampling_coef)
        self.default_cfg_strength = float(default_cfg_strength)
        self.default_speed_preset = default_speed_preset.strip().lower() or "normal"

        self._ready = False
        self._api_cls: type | None = None
        self._model: Any = None
        self._infer_lock = asyncio.Lock()

    @property
    def ready(self) -> bool:
        return self._ready

    async def prewarm(self) -> None:
        if self.mode != "real":
            raise RuntimeError("F5_TTS_ENGINE_MODE must be set to 'real'. Mock mode is disabled.")
        if not self.upstream_dir.exists():
            raise RuntimeError(f"F5 upstream directory not found: {self.upstream_dir}")

        src_dir = self.upstream_dir / "src"
        if not src_dir.exists():
            raise RuntimeError(f"F5 upstream src directory not found: {src_dir}")

        src_dir_str = str(src_dir.resolve())
        if src_dir_str not in sys.path:
            sys.path.insert(0, src_dir_str)

        try:
            module = self._import_f5_api_module()
            self._api_cls = getattr(module, "F5TTS")
        except Exception as error:
            raise RuntimeError(
                "Cannot import f5_tts.api.F5TTS from vendor/F5-TTS. "
                "Install upstream dependencies first."
            ) from error

        ckpt_file = self._resolve_checkpoint_file()
        vocab_file = self._resolve_vocab_file()
        self.hf_cache_dir.mkdir(parents=True, exist_ok=True)
        resolved_vocoder_dir = self._ensure_local_vocoder_assets()

        logger.info("Loading F5 model model=%s ckpt=%s", self.model_name, ckpt_file)
        if resolved_vocoder_dir is not None:
            logger.info("Using local Vocos assets path=%s", resolved_vocoder_dir)
        self._model = await asyncio.to_thread(
            self._create_model,
            ckpt_file,
            vocab_file,
        )
        self._ready = True
        logger.info("F5 model is ready")

    def _import_f5_api_module(self):
        try:
            return importlib.import_module("f5_tts.api")
        except Exception as first_error:
            logger.warning(
                "F5 upstream import failed once; retrying with inference-only trainer stub: %s",
                first_error,
            )
            self._install_inference_trainer_stub()
            sys.modules.pop("f5_tts.api", None)
            sys.modules.pop("f5_tts.model", None)
            return importlib.import_module("f5_tts.api")

    @staticmethod
    def _install_inference_trainer_stub() -> None:
        if TRAINER_MODULE_NAME in sys.modules:
            return

        trainer_module = types.ModuleType(TRAINER_MODULE_NAME)

        class _InferenceOnlyTrainer:
            def __init__(self, *_, **__) -> None:
                raise RuntimeError("F5 Trainer is unavailable in the inference service runtime")

        trainer_module.Trainer = _InferenceOnlyTrainer
        sys.modules[TRAINER_MODULE_NAME] = trainer_module

    async def synthesize(
        self,
        *,
        text: str,
        voice: str,
        ref_audio_path: str,
        ref_text: str,
        volume_level: float = 50.0,
        cfg_strength: float | None = None,
        speed_preset: str | None = None,
        remove_silence: bool = False,
        metadata: dict | None = None,
    ) -> SynthesisResult:
        if not self._ready or self._model is None:
            raise RuntimeError("F5 engine is not ready")
        if not text or not text.strip():
            raise ValueError("Text is empty")

        ref_audio = Path(ref_audio_path).resolve()
        if not ref_audio.exists():
            raise ValueError(f"Reference audio not found: {ref_audio}")

        preset = (speed_preset or self.default_speed_preset or "normal").strip().lower()
        detected_language = self._detect_language(text)
        text_length = self._text_length_without_spaces(text)
        speed_factor = self._resolve_speed_factor(
            preset=preset,
            language=detected_language,
            text_length=text_length,
        )
        nfe_step = self._resolve_nfe_step(text_length)

        cfg_value = float(cfg_strength) if cfg_strength is not None else float(self.default_cfg_strength)
        request_logger = get_request_logger(
            logger,
            merge_request_context(metadata or {}, selected_voice=voice, voice=voice),
        )

        started = perf_counter()
        request_logger.info(
            "Engine synthesis started model=%s cfg_strength=%s speed_factor=%s nfe_step=%s language=%s text_length_no_spaces=%s remove_silence=%s",
            self.model_name,
            cfg_value,
            round(speed_factor, 4),
            nfe_step,
            detected_language,
            text_length,
            bool(remove_silence),
        )
        async with self._infer_lock:
            wav, sample_rate, used_speed_factor, used_nfe_step = await asyncio.to_thread(
                self._infer_sync,
                str(ref_audio),
                (ref_text or "").strip(),
                text.strip(),
                cfg_value,
                speed_factor,
                nfe_step,
                bool(remove_silence),
                request_logger,
            )
        wav = self._apply_legacy_tail_shaping(wav, sample_rate)
        wav = self._apply_volume(wav, float(volume_level))
        audio_bytes = self._wav_to_bytes(wav, sample_rate)

        duration_sec = len(wav) / float(sample_rate) if sample_rate > 0 else 0.0
        elapsed = perf_counter() - started
        request_logger.info(
            "Engine synthesis finished duration_sec=%s sample_rate=%s inference_time_sec=%s",
            round(max(0.0, duration_sec), 3),
            int(sample_rate),
            round(elapsed, 4),
        )

        return SynthesisResult(
            audio_bytes=audio_bytes,
            duration_sec=max(0.0, duration_sec),
            sample_rate=int(sample_rate),
            voice=voice,
            meta={
                "engine_mode": self.mode,
                "inference_time_sec": round(elapsed, 4),
                "cfg_strength": cfg_value,
                "speed_preset": preset,
                "speed_factor": round(used_speed_factor, 4),
                "nfe_step": int(used_nfe_step),
                "detected_language": detected_language,
                "text_length_no_spaces": text_length,
                "ref_audio_path": str(ref_audio),
                "model_name": self.model_name,
            },
        )

    def _create_model(self, checkpoint_file: str, vocab_file: str):
        assert self._api_cls is not None
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "ckpt_file": checkpoint_file,
            "vocab_file": vocab_file,
            "ode_method": self.ode_method,
            "use_ema": self.use_ema,
            "hf_cache_dir": str(self.hf_cache_dir),
        }
        if self._has_vocoder_assets(self.vocoder_local_dir):
            kwargs["vocoder_local_path"] = str(self.vocoder_local_dir)
        if self.device:
            kwargs["device"] = self.device
        return self._api_cls(**kwargs)

    def _has_vocoder_assets(self, directory: Path) -> bool:
        return (directory / "config.yaml").exists() and (directory / "pytorch_model.bin").exists()

    def _ensure_local_vocoder_assets(self) -> Path | None:
        if self._has_vocoder_assets(self.vocoder_local_dir):
            return self.vocoder_local_dir

        if self._seed_vocoder_dir_from_hf_cache() and self._has_vocoder_assets(self.vocoder_local_dir):
            logger.info("Seeded local Vocos mirror from HF cache path=%s", self.vocoder_local_dir)
            return self.vocoder_local_dir

        if self._download_vocoder_to_local_dir() and self._has_vocoder_assets(self.vocoder_local_dir):
            logger.info("Bootstrapped local Vocos mirror repo=%s path=%s", self.vocoder_repo_id, self.vocoder_local_dir)
            return self.vocoder_local_dir

        logger.warning("Local Vocos assets are unavailable; upstream may fall back to Hugging Face download.")
        return None

    def _seed_vocoder_dir_from_hf_cache(self) -> bool:
        snapshot_root = self.hf_cache_dir / f"models--{self.vocoder_repo_id.replace('/', '--')}" / "snapshots"
        if not snapshot_root.exists():
            return False

        snapshots = [path for path in snapshot_root.iterdir() if path.is_dir()]
        snapshots.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        for snapshot in snapshots:
            config_path = snapshot / "config.yaml"
            model_path = snapshot / "pytorch_model.bin"
            if not (config_path.exists() and model_path.exists()):
                continue

            self.vocoder_local_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(config_path, self.vocoder_local_dir / "config.yaml")
            shutil.copy2(model_path, self.vocoder_local_dir / "pytorch_model.bin")
            return True

        return False

    def _download_vocoder_to_local_dir(self) -> bool:
        try:
            from huggingface_hub import hf_hub_download
        except Exception as error:
            logger.warning("Could not import huggingface_hub for Vocos bootstrap: %s", error)
            return False

        try:
            self.vocoder_local_dir.mkdir(parents=True, exist_ok=True)
            for filename in ("config.yaml", "pytorch_model.bin"):
                downloaded_file = Path(
                    hf_hub_download(
                        repo_id=self.vocoder_repo_id,
                        cache_dir=str(self.hf_cache_dir),
                        filename=filename,
                    )
                )
                shutil.copy2(downloaded_file, self.vocoder_local_dir / filename)
            return True
        except Exception as error:
            logger.warning("Failed to bootstrap local Vocos mirror repo=%s: %s", self.vocoder_repo_id, error)
            return False

    def _resolve_checkpoint_file(self) -> str:
        if self.checkpoint_file:
            candidate = Path(self.checkpoint_file).resolve()
            if not candidate.exists():
                raise RuntimeError(f"Checkpoint file not found: {candidate}")
            return str(candidate)

        if not self.russian_weights_dir.exists():
            raise RuntimeError(f"Russian weights directory not found: {self.russian_weights_dir}")

        preferred: list[Path] = []
        preferred.extend(self.russian_weights_dir.rglob("model_last_inference.safetensors"))
        preferred.extend(self.russian_weights_dir.rglob("*inference*.safetensors"))
        preferred.extend(self.russian_weights_dir.rglob("*.safetensors"))
        preferred.extend(self.russian_weights_dir.rglob("*.pt"))

        if not preferred:
            raise RuntimeError(
                "Cannot find F5 checkpoint under models/F5-TTS_RUSSIAN. "
                "Set F5_TTS_CHECKPOINT_FILE explicitly."
            )

        preferred.sort(key=lambda path: (len(str(path)), str(path)))
        return str(preferred[0].resolve())

    def _resolve_vocab_file(self) -> str:
        if self.vocab_file:
            candidate = Path(self.vocab_file).resolve()
            if not candidate.exists():
                raise RuntimeError(f"Vocab file not found: {candidate}")
            return str(candidate)

        candidates = list(self.russian_weights_dir.rglob("vocab.txt"))
        if not candidates:
            vendor_vocab = self.upstream_dir / "src" / "f5_tts" / "infer" / "examples" / "vocab.txt"
            if vendor_vocab.exists():
                return str(vendor_vocab.resolve())
            raise RuntimeError(
                "Cannot find vocab.txt under models/F5-TTS_RUSSIAN and vendor fallback is missing. "
                "Set F5_TTS_VOCAB_FILE explicitly."
            )

        candidates.sort(key=lambda path: (len(str(path)), str(path)))
        return str(candidates[0].resolve())

    def _infer_sync(
        self,
        ref_audio_path: str,
        ref_text: str,
        gen_text: str,
        cfg_strength: float,
        speed_factor: float,
        nfe_step: int,
        remove_silence: bool,
        request_logger,
    ) -> tuple[Any, int, float, int]:
        assert self._model is not None
        infer_kwargs = {
            "ref_file": ref_audio_path,
            "ref_text": ref_text,
            "gen_text": gen_text,
            "show_info": lambda *messages: self._log_upstream_info(request_logger, *messages),
            "progress": _LoggingProgress(request_logger),
            "target_rms": self.target_rms,
            "cross_fade_duration": self.cross_fade_duration,
            "sway_sampling_coef": self.sway_sampling_coef,
            "cfg_strength": cfg_strength,
            "nfe_step": nfe_step,
            "speed": speed_factor,
            "fix_duration": None,
            "remove_silence": remove_silence,
        }
        try:
            wav, sample_rate, _ = self._model.infer(**infer_kwargs)
            return wav, int(sample_rate), float(speed_factor), int(nfe_step)
        except RuntimeError as error:
            if not self._is_cuda_runtime_error(error):
                standardized_ref_audio = self._create_standard_reference_audio_retry(
                    ref_audio_path,
                    request_logger,
                    error,
                )
                if standardized_ref_audio is None:
                    raise
                try:
                    retry_kwargs = dict(infer_kwargs)
                    retry_kwargs["ref_file"] = standardized_ref_audio
                    wav, sample_rate, _ = self._model.infer(**retry_kwargs)
                    return wav, int(sample_rate), float(speed_factor), int(nfe_step)
                finally:
                    Path(standardized_ref_audio).unlink(missing_ok=True)
            request_logger.warning(
                "CUDA inference failed; retrying with legacy fallback speed=%s nfe_step=%s error=%s",
                LEGACY_FALLBACK_SPEED,
                LEGACY_FALLBACK_NFE_STEP,
                error,
            )
            self._clear_cuda_cache()
            fallback_kwargs = {
                "ref_file": ref_audio_path,
                "ref_text": ref_text,
                "gen_text": gen_text,
                "show_info": infer_kwargs["show_info"],
                "progress": _LoggingProgress(request_logger),
                "speed": LEGACY_FALLBACK_SPEED,
                "nfe_step": LEGACY_FALLBACK_NFE_STEP,
            }
            wav, sample_rate, _ = self._model.infer(**fallback_kwargs)
            return wav, int(sample_rate), LEGACY_FALLBACK_SPEED, LEGACY_FALLBACK_NFE_STEP

    def _create_standard_reference_audio_retry(
        self,
        ref_audio_path: str,
        request_logger,
        error: RuntimeError,
    ) -> str | None:
        if not self._is_reference_audio_load_error(error):
            return None

        ref_audio = Path(ref_audio_path).resolve()
        fd, temp_name = tempfile.mkstemp(prefix="f5_ref_", suffix=".wav")
        os.close(fd)
        try:
            Path(temp_name).unlink(missing_ok=True)
            convert_audio_to_wav(
                ref_audio,
                Path(temp_name),
                sample_rate=REFERENCE_AUDIO_SAMPLE_RATE,
                channels=1,
            )
            request_logger.warning(
                "Reference audio load failed in upstream; retrying with normalized WAV source=%s temp=%s error=%s",
                ref_audio,
                temp_name,
                error,
            )
            return temp_name
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise

    @staticmethod
    def _log_upstream_info(request_logger, *messages: Any) -> None:
        text = " ".join(str(message or "").strip() for message in messages if str(message or "").strip())
        if not text:
            return
        request_logger.info("F5 upstream: %s", text)

    @staticmethod
    def _detect_language(text: str) -> str:
        cyrillic_count = len(CYRILLIC_RE.findall(text or ""))
        latin_count = len(LATIN_RE.findall(text or ""))
        if cyrillic_count > latin_count:
            return "russian"
        if latin_count > cyrillic_count:
            return "english"
        if cyrillic_count > 0:
            return "russian"
        return "russian"

    @staticmethod
    def _text_length_without_spaces(text: str) -> int:
        return len(re.sub(r"\s+", "", text or ""))

    @classmethod
    def _resolve_speed_factor(cls, *, preset: str, language: str, text_length: int) -> float:
        try:
            numeric = float(preset)
        except Exception:
            numeric = None
        if numeric is not None:
            return max(0.1, min(2.0, numeric))

        normalized_preset = preset if preset in LEGACY_SPEED_PRESETS else "normal"
        speed_values = LEGACY_SPEED_PRESETS[normalized_preset].get(language) or LEGACY_SPEED_PRESETS[normalized_preset]["russian"]
        bucket_index = 0
        for threshold in LEGACY_TEXT_LENGTH_BUCKETS:
            if text_length <= threshold:
                break
            bucket_index += 1
        bucket_index = min(bucket_index, len(speed_values) - 1)
        return max(0.1, min(2.0, float(speed_values[bucket_index])))

    def _resolve_nfe_step(self, text_length: int) -> int:
        auto_nfe_step = LEGACY_LONG_TEXT_NFE_STEP if text_length > LEGACY_LONG_TEXT_THRESHOLD else LEGACY_SHORT_TEXT_NFE_STEP
        return max(1, min(int(self.nfe_step), auto_nfe_step))

    @staticmethod
    def _is_cuda_runtime_error(error: RuntimeError) -> bool:
        return "cuda" in str(error).lower()

    @staticmethod
    def _is_reference_audio_load_error(error: RuntimeError) -> bool:
        text = str(error or "").lower()
        markers = (
            "torchaudio",
            "failed to open",
            "error opening",
            "could not open",
            "invalid data",
            "format not recognised",
            "format not recognized",
            "no backend is available",
            "appropriate backend",
            "ffmpeg",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _clear_cuda_cache() -> None:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
        except Exception:
            return

    @staticmethod
    def _apply_legacy_tail_shaping(wav: Any, sample_rate: int):
        import numpy as np

        if int(sample_rate) <= 0:
            return np.asarray(wav, dtype=np.float32)

        arr = np.asarray(wav, dtype=np.float32)
        silence_samples = int(sample_rate * (LEGACY_MIN_TAIL_SILENCE_MS / 1000.0))
        padded = np.concatenate([arr, np.zeros(silence_samples, dtype=np.float32)])

        fade_samples = int(sample_rate * LEGACY_FADE_OUT_SEC)
        if fade_samples > 0 and len(padded) > fade_samples:
            fade = np.cos(np.linspace(0, np.pi / 2, fade_samples, dtype=np.float32))
            padded[-fade_samples:] *= fade

        post_silence_samples = int(sample_rate * LEGACY_POST_FADE_SILENCE_SEC)
        if post_silence_samples > 0:
            padded = np.concatenate([padded, np.zeros(post_silence_samples, dtype=np.float32)])
        return padded

    @staticmethod
    def _apply_volume(wav: Any, volume_level: float):
        import numpy as np

        gain = max(0.0, min(2.0, volume_level / 50.0))
        arr = np.asarray(wav, dtype=np.float32)
        if gain != 1.0:
            arr = np.clip(arr * gain, -1.0, 1.0)
        return arr

    @staticmethod
    def _wav_to_bytes(wav: Any, sample_rate: int) -> bytes:
        import numpy as np
        import soundfile as sf

        arr = np.asarray(wav, dtype=np.float32)
        with io.BytesIO() as buff:
            sf.write(buff, arr, sample_rate, format="WAV", subtype="PCM_16")
            return buff.getvalue()
