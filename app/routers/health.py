from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health")
async def legacy_health(request: Request) -> dict[str, str | bool]:
    engine = request.app.state.engine
    return {
        "status": "healthy" if engine.ready else "degraded",
        "service": "f5_tts",
        "tts_engine_loaded": bool(engine.ready),
    }


@router.get("/api/health")
async def api_health_alias(request: Request) -> dict[str, str | bool]:
    return await legacy_health(request)


@router.get("/health/live", response_model=HealthResponse)
async def live(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(status="ok", service="f5-tts-service", mode=settings.engine_mode)


@router.get("/health/ready", response_model=HealthResponse)
async def ready(request: Request) -> HealthResponse:
    engine = request.app.state.engine
    status = "ok" if engine.ready else "degraded"
    return HealthResponse(status=status, service="f5-tts-service", mode=engine.mode)
