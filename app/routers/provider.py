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
    requested_format = str(payload.format or "wav").strip().lower()
    if requested_format != "wav":
        return ProviderSynthesizeResponse(
            success=False,
            audio_url=None,
            voice=payload.voice,
            selected_voice=payload.voice,
            tts_type="ai_f5",
            duration=None,
            error="Unsupported format. Only 'wav' is allowed",
            request_id=request_id,
            meta={"request_in_sec": 0.0},
        )
    max_len = max(1, int(request.app.state.settings.max_input_text_length))
    if len(payload.text or "") > max_len:
        return ProviderSynthesizeResponse(
            success=False,
            audio_url=None,
            voice=payload.voice,
            selected_voice=payload.voice,
            tts_type="ai_f5",
            duration=None,
            error=f"Text too long. Maximum {max_len} characters",
            request_id=request_id,
            meta={"request_in_sec": 0.0},
        )

    raw_result = await request.app.state.provider_synthesize(payload.model_dump(mode="json"))
    elapsed = perf_counter() - started
    if not raw_result.get("success"):
        return ProviderSynthesizeResponse(
            success=False,
            audio_url=None,
            voice=payload.voice,
            selected_voice=payload.voice,
            tts_type="ai_f5",
            duration=None,
            error=str(raw_result.get("error") or "Synthesis failed"),
            request_id=request_id,
            meta={"request_in_sec": round(elapsed, 4)},
        )

    return ProviderSynthesizeResponse(
        success=True,
        audio_url=raw_result.get("audio_url"),
        voice=raw_result.get("voice"),
        selected_voice=raw_result.get("selected_voice"),
        tts_type="ai_f5",
        duration=raw_result.get("duration"),
        request_id=request_id,
        meta={
            "request_in_sec": round(elapsed, 4),
            **(raw_result.get("meta") or {}),
        },
    )
