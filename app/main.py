from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .config import Settings, get_settings
from .engine.f5_engine import F5Engine
from .limits_store import TTSLimitsStore
from .routers import admin, health, provider, tts_compat
from .ru_pipeline import RuPipeline
from .storage.audio_store import AudioStore
from .synthesis_context import resolve_synthesis_context
from .transcriber import ReferenceTranscriber
from .voice_store import VoiceStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("f5-tts-service")


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    return bool(value)


def _make_provider_synthesize_fn(app: FastAPI):
    async def _provider_synthesize(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            text_ru = app.state.ru_pipeline.process(payload["text"])
            if not text_ru:
                raise ValueError("Text is empty after RU preprocessing")
            synth_context = await resolve_synthesis_context(app, payload)
            metadata = payload.get("metadata") or {}
            if "remove_silence" in payload:
                remove_silence = _as_bool(payload.get("remove_silence"))
            else:
                remove_silence = _as_bool(metadata.get("remove_silence"))
            result = await app.state.engine.synthesize(
                text=text_ru,
                voice=synth_context["selected_voice"],
                ref_audio_path=synth_context["reference_audio_path"],
                ref_text=synth_context["reference_text"],
                volume_level=float(payload.get("volume_level", 50.0)),
                cfg_strength=float(synth_context["cfg_strength"]),
                speed_preset=synth_context["speed_preset"],
                remove_silence=remove_silence,
                metadata=metadata,
            )
            filename = app.state.audio_store.save_bytes(result.audio_bytes, suffix=".wav")
            return {
                "success": True,
                "audio_url": f"/api/tts/audio/{filename}",
                "duration": round(result.duration_sec, 3),
                "voice": synth_context["selected_voice"],
                "selected_voice": synth_context["selected_voice"],
                "meta": result.meta,
            }
        except Exception as error:  # pragma: no cover - safety
            logger.exception("Synthesis error")
            return {"success": False, "error": str(error)}

    return _provider_synthesize


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = get_settings()
    app.state.settings = settings
    if not settings.api_keys:
        raise RuntimeError("F5_TTS_SERVICE_API_KEYS must be set (comma-separated API keys)")

    audio_store = AudioStore(settings.audio_path)
    voices_dir = settings.voices_dir_path
    voice_store = VoiceStore(
        settings.voices_state_path,
        voices_dir,
        database_url=settings.database_url,
        database_echo=settings.database_echo,
    )
    limits_store = TTSLimitsStore(
        settings.limits_state_path,
        default_max_text_length=settings.limit_default_max_text_length,
        default_daily_limit=settings.limit_default_daily_requests,
        default_priority_level=settings.limit_default_priority_level,
        default_tts_enabled=settings.limit_default_tts_enabled,
        retention_days=settings.limits_retention_days,
        database_url=settings.database_url,
        database_echo=settings.database_echo,
    )
    try:
        await voice_store.startup()
        await limits_store.startup()

        ru_pipeline = RuPipeline.create(settings.ru_yo_dict_path, settings.ru_accents_path)
        engine = F5Engine(
            mode=settings.engine_mode,
            upstream_dir=settings.upstream_path,
            russian_weights_dir=settings.russian_weights_path,
            model_name=settings.model_name,
            checkpoint_file=settings.checkpoint_file,
            vocab_file=settings.vocab_file,
            hf_cache_dir=settings.hf_cache_path,
            device=settings.device,
            ode_method=settings.ode_method,
            use_ema=settings.use_ema,
            target_rms=settings.target_rms,
            cross_fade_duration=settings.cross_fade_duration,
            nfe_step=settings.nfe_step,
            sway_sampling_coef=settings.sway_sampling_coef,
            default_cfg_strength=settings.f5_default_cfg_strength,
            default_speed_preset=settings.f5_default_speed_preset,
        )
        transcriber = ReferenceTranscriber(
            enabled=settings.transcriber_enabled,
            model_name=settings.transcriber_model,
            device=settings.transcriber_device,
            compute_type=settings.transcriber_compute_type,
            language=settings.transcriber_language,
        )

        app.state.audio_store = audio_store
        app.state.voice_store = voice_store
        app.state.limits_store = limits_store
        app.state.ru_pipeline = ru_pipeline
        app.state.engine = engine
        app.state.transcriber = transcriber
        app.state.voice_files_dir = voices_dir
        app.state.provider_synthesize = _make_provider_synthesize_fn(app)

        if settings.enable_prewarm:
            try:
                await engine.prewarm()
            except Exception as error:
                logger.warning("Prewarm failed: %s", error)
                raise
        if settings.transcriber_enabled and settings.transcriber_preload:
            try:
                await transcriber.prewarm()
            except Exception as error:
                logger.warning("Transcriber prewarm failed: %s", error)
                raise
        yield
    finally:
        await limits_store.close()
        await voice_store.close()


app = FastAPI(
    title="f5-tts-service",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(provider.router)
app.include_router(tts_compat.router)
app.include_router(admin.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "f5-tts-service", "status": "ok"}


@app.exception_handler(ValueError)
async def value_error_handler(_, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})
