from __future__ import annotations

import asyncio
import importlib
import io
import logging
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

from .base import BaseTtsEngine, SynthesisResult

logger = logging.getLogger(__name__)

SPEED_FACTORS: dict[str, float] = {
    "very_slow": 0.72,
    "slow": 0.86,
    "normal": 1.0,
    "fast": 1.18,
    "very_fast": 1.34,
}


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
            module = importlib.import_module("f5_tts.api")
            self._api_cls = getattr(module, "F5TTS")
        except Exception as error:
            raise RuntimeError(
                "Cannot import f5_tts.api.F5TTS from vendor/F5-TTS. "
                "Install upstream dependencies first."
            ) from error

        ckpt_file = self._resolve_checkpoint_file()
        vocab_file = self._resolve_vocab_file()
        self.hf_cache_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Loading F5 model model=%s ckpt=%s", self.model_name, ckpt_file)
        self._model = await asyncio.to_thread(
            self._create_model,
            ckpt_file,
            vocab_file,
        )
        self._ready = True
        logger.info("F5 model is ready")

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
        speed_factor = SPEED_FACTORS.get(preset)
        if speed_factor is None:
            try:
                speed_factor = float(preset)
            except Exception:
                speed_factor = SPEED_FACTORS["normal"]
        speed_factor = max(0.1, min(2.0, float(speed_factor)))

        cfg_value = float(cfg_strength) if cfg_strength is not None else float(self.default_cfg_strength)

        started = perf_counter()
        async with self._infer_lock:
            wav, sample_rate = await asyncio.to_thread(
                self._infer_sync,
                str(ref_audio),
                (ref_text or "").strip(),
                text.strip(),
                cfg_value,
                speed_factor,
                bool(remove_silence),
            )
        wav = self._apply_volume(wav, float(volume_level))
        audio_bytes = self._wav_to_bytes(wav, sample_rate)

        duration_sec = len(wav) / float(sample_rate) if sample_rate > 0 else 0.0
        elapsed = perf_counter() - started

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
                "speed_factor": round(speed_factor, 4),
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
        if self.device:
            kwargs["device"] = self.device
        return self._api_cls(**kwargs)

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
        remove_silence: bool,
    ) -> tuple[Any, int]:
        assert self._model is not None
        wav, sample_rate, _ = self._model.infer(
            ref_file=ref_audio_path,
            ref_text=ref_text,
            gen_text=gen_text,
            show_info=lambda *_: None,
            progress=None,
            target_rms=self.target_rms,
            cross_fade_duration=self.cross_fade_duration,
            sway_sampling_coef=self.sway_sampling_coef,
            cfg_strength=cfg_strength,
            nfe_step=self.nfe_step,
            speed=speed_factor,
            fix_duration=None,
            remove_silence=remove_silence,
        )
        return wav, int(sample_rate)

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
