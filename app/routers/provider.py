from __future__ import annotations

import uuid
from time import perf_counter

from fastapi import APIRouter, Depends, Request

from ..auth import verify_api_key
from ..schemas import ProviderSynthesizeRequest, ProviderSynthesizeResponse

router = APIRouter(prefix="/v1", tags=["provider"], dependencies=[Depends(verify_api_key)])


@router.post("/synthesize", response_model=ProviderSynthesizeResponse)
async def synthesize(request: Request, payload: ProviderSynthesizeRequest) -> ProviderSynthesizeResponse:
    started = perf_counter()
    request_id = uuid.uuid4().hex

    text_ru = request.app.state.ru_pipeline.process(payload.text)
    result = await request.app.state.engine.synthesize(
        text=text_ru,
        voice=payload.voice,
        volume_level=payload.volume_level,
        metadata=payload.metadata,
    )
    filename = request.app.state.audio_store.save_bytes(result.audio_bytes, suffix=".wav")
    audio_url = f"/api/tts/audio/{filename}"

    elapsed = perf_counter() - started
    return ProviderSynthesizeResponse(
        success=True,
        audio_url=audio_url,
        voice=result.voice,
        selected_voice=result.voice,
        tts_type="ai_f5",
        duration=round(result.duration_sec, 3),
        request_id=request_id,
        meta={
            "request_in_sec": round(elapsed, 4),
            "sample_rate": result.sample_rate,
            **result.meta,
        },
    )

