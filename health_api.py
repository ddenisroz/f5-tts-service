"""Health and diagnostics endpoints for F5_tts."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from background_tasks import background_task_manager
from database import get_db
from file_manager import file_manager
from monitoring import tts_monitor
from tts_engine import tts_engine_manager

logger = logging.getLogger(__name__)

health_router = APIRouter(tags=["health"])
api_health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health_check():
    """Basic liveness/readiness endpoint."""
    try:
        tts_engine_loaded = tts_engine_manager.is_ready()
    except Exception:
        logger.exception("Error checking TTS engine readiness")
        tts_engine_loaded = (
            getattr(tts_engine_manager, "is_initialized", False)
            and tts_engine_manager.tts_engine is not None
        )

    return {
        "status": "healthy",
        "service": "f5_tts",
        "version": "1.0.0",
        "tts_engine_loaded": tts_engine_loaded,
    }


@health_router.get("/health/live")
async def health_live():
    """Liveness probe: process is up."""
    return {"status": "alive", "service": "f5_tts"}


@health_router.get("/health/ready")
async def health_ready(db: Session = Depends(get_db)):
    """Readiness probe: dependencies are available."""
    checks = {
        "database": "unknown",
        "tts_engine": "unknown",
        "background_tasks": "unknown",
    }
    ready = True

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        logger.exception("Readiness DB check failed")
        checks["database"] = "error"
        ready = False

    try:
        engine_ready = bool(tts_engine_manager.is_ready())
        checks["tts_engine"] = "ok" if engine_ready else "not_ready"
        ready = ready and engine_ready
    except Exception:
        logger.exception("Readiness TTS engine check failed")
        checks["tts_engine"] = "error"
        ready = False

    try:
        bg_running = bool(background_task_manager.is_running())
        checks["background_tasks"] = "ok" if bg_running else "not_running"
        ready = ready and bg_running
    except Exception:
        logger.exception("Readiness background tasks check failed")
        checks["background_tasks"] = "error"
        ready = False

    if ready:
        return {"status": "ready", "service": "f5_tts", "checks": checks}
    raise HTTPException(status_code=503, detail={"status": "not_ready", "service": "f5_tts", "checks": checks})


@api_health_router.get("/health")
async def api_health_check_alias():
    """Compatibility alias used by bot_service."""
    return await health_check()


@health_router.get("/detailed")
async def detailed_health_check(db: Session = Depends(get_db)):
    """Detailed component-level health view."""
    try:
        db_status = "healthy"
        try:
            db.execute(text("SELECT 1"))
        except Exception:
            logger.exception("Database health check failed")
            db_status = "error"

        tts_status = "healthy" if tts_engine_manager.is_initialized() else "not_initialized"
        file_status = "healthy" if file_manager.is_initialized() else "not_initialized"
        bg_status = "running" if background_task_manager.is_running() else "stopped"

        return {
            "status": "healthy",
            "components": {
                "database": db_status,
                "tts_engine": tts_status,
                "file_manager": file_status,
                "background_tasks": bg_status,
            },
            "metrics": tts_monitor.get_metrics(),
        }
    except Exception:
        logger.exception("Detailed health check failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@health_router.get("/metrics")
async def get_metrics():
    """Return monitoring metrics."""
    try:
        return {"status": "success", "metrics": tts_monitor.get_metrics()}
    except Exception:
        logger.exception("Metrics endpoint failed")
        raise HTTPException(status_code=500, detail="Internal server error")
