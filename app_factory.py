"""Application factory for the F5_tts service."""

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()

# Keep HuggingFace runtime deterministic in local/docker runs.
for env_name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(env_name, None)

cache_dir = Path("f5_tts_cache").resolve()
os.environ["HF_HOME"] = str(cache_dir)
os.environ["HUGGINGFACE_HUB_CACHE"] = str(cache_dir)

service_root = Path(__file__).resolve().parent
if str(service_root) not in sys.path:
    sys.path.insert(0, str(service_root))

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI app instance."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        background_task_manager = None
        tts_engine_manager = None
        tts_monitor = None

        logger.info("[START] F5_tts startup")
        try:
            from database import init_db

            init_db()
            logger.info("[OK] Database initialized")

            from tts_engine import tts_engine_manager as engine_manager

            tts_engine_manager = engine_manager
            await tts_engine_manager.initialize()
            logger.info("[OK] TTS engine initialized")

            # Import triggers FileManager initialization.
            from file_manager import file_manager  # noqa: F401

            logger.info("[OK] File manager initialized")

            from background_tasks import background_task_manager as bg_manager

            background_task_manager = bg_manager
            await background_task_manager.start()
            logger.info("[OK] Background tasks started")

            from monitoring import tts_monitor as monitor

            tts_monitor = monitor
            tts_monitor.start_monitoring(interval=30)
            logger.info("[OK] Monitoring started")

        except Exception:
            logger.exception("[ERROR] Startup failed")
            raise

        yield

        logger.info("[SHUTDOWN] F5_tts shutdown")
        try:
            if background_task_manager is not None:
                await background_task_manager.stop()
                logger.info("[OK] Background tasks stopped")

            if tts_engine_manager is not None:
                await tts_engine_manager.shutdown()
                logger.info("[OK] TTS engine stopped")

            if tts_monitor is not None:
                tts_monitor.stop_monitoring()
                logger.info("[OK] Monitoring stopped")

        except Exception:
            logger.exception("[ERROR] Shutdown failed")

    app = FastAPI(
        title="F5_tts Service",
        description="Advanced F5 Text-to-Speech service",
        version="1.0.0",
        lifespan=lifespan,
    )

    from config import config

    allowed_origins = [origin.strip() for origin in config.cors_origins.split(",") if origin.strip()]
    if not allowed_origins:
        allowed_origins = ["http://localhost:5173"]
    allow_credentials = "*" not in allowed_origins
    if not allow_credentials:
        logger.warning("CORS wildcard origin configured; credentials disabled")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from admin_api import admin_router
    from api_endpoints import tts_api
    from api_endpoints_voice_enabled import voice_enabled_router
    from health_api import api_health_router, health_router
    from tts_control_api import router as tts_control_router

    app.include_router(tts_api, prefix="/api/tts")
    app.include_router(voice_enabled_router, prefix="/api/tts")
    app.include_router(health_router, prefix="")
    app.include_router(api_health_router, prefix="/api")
    app.include_router(admin_router, prefix="/api/admin")
    app.include_router(tts_control_router, prefix="")

    config.audio_path.mkdir(parents=True, exist_ok=True)
    app.mount("/audio", StaticFiles(directory=str(config.audio_path)), name="audio")

    return app
