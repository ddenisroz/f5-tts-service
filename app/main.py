from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .config import Settings, get_settings
from .engine.f5_engine import F5Engine
from .routers import admin, health, provider, tts_compat
from .ru_pipeline import RuPipeline
from .storage.audio_store import AudioStore
from .voice_store import VoiceStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("f5-tts-service")


def _make_provider_synthesize_fn(app: FastAPI):
    async def _provider_synthesize(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            text_ru = app.state.ru_pipeline.process(payload["text"])
            result = await app.state.engine.synthesize(
                text=text_ru,
                voice=payload.get("voice") or "female_1",
                volume_level=float(payload.get("volume_level", 50.0)),
                metadata=payload.get("metadata") or {},
            )
            filename = app.state.audio_store.save_bytes(result.audio_bytes, suffix=".wav")
            return {
                "success": True,
                "audio_url": f"/api/tts/audio/{filename}",
                "duration": round(result.duration_sec, 3),
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

    audio_store = AudioStore(settings.audio_path)
    voice_store = VoiceStore(settings.voices_state_path, Path("data/voices").resolve())
    ru_pipeline = RuPipeline.create(settings.ru_yo_dict_path, settings.ru_accents_path)
    engine = F5Engine(
        mode=settings.engine_mode,
        upstream_dir=Path(settings.upstream_dir).resolve(),
        russian_weights_dir=Path(settings.russian_weights_dir).resolve(),
    )
    app.state.audio_store = audio_store
    app.state.voice_store = voice_store
    app.state.ru_pipeline = ru_pipeline
    app.state.engine = engine
    app.state.voice_files_dir = Path("data/voices").resolve()
    app.state.provider_synthesize = _make_provider_synthesize_fn(app)

    if settings.enable_prewarm:
        try:
            await engine.prewarm()
        except Exception as error:
            logger.warning("Prewarm failed: %s", error)
    yield


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
