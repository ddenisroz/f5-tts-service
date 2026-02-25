from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    service: str
    mode: str | None = None


class ProviderSynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    voice: str = Field(default="female_1", max_length=120)
    tenant_id: str | None = Field(default=None, max_length=200)
    channel_name: str | None = Field(default=None, max_length=120)
    author: str | None = Field(default=None, max_length=120)
    user_id: int | None = None
    volume_level: float = Field(default=50.0, ge=0.0, le=100.0)
    format: str = Field(default="wav")
    cfg_strength: float | None = None
    speed_preset: str | None = None
    remove_silence: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderSynthesizeResponse(BaseModel):
    success: bool
    audio_url: str | None = None
    voice: str | None = None
    selected_voice: str | None = None
    tts_type: str = "ai_f5"
    duration: float | None = None
    error: str | None = None
    request_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class CompatSynthesizeChannelRequest(BaseModel):
    channel_name: str = Field(..., min_length=1, max_length=120)
    text: str = Field(..., min_length=1, max_length=10000)
    author: str = Field(default="unknown", max_length=120)
    user_id: int | None = None
    volume_level: float = Field(default=50.0, ge=0.0, le=100.0)
    tts_settings: dict[str, Any] = Field(default_factory=dict)
    word_filter: list[str] = Field(default_factory=list)
    blocked_users: list[str] = Field(default_factory=list)
    provider: str | None = None
    voice: str | None = None


class UserTtsLimitsPatch(BaseModel):
    max_text_length: int | None = None
    daily_limit: int | None = None
    priority_level: int | None = None
    tts_enabled: bool | None = None


class VoiceRecord(BaseModel):
    id: int
    name: str
    file_path: str = ""
    voice_type: str = "global"
    owner_id: int | None = None
    is_public: bool = False
    is_active: bool = True
    reference_text: str | None = None
    created_at: str | None = None
    cfg_strength: float | None = None
    speed_preset: str | None = None
    enabled_user_ids: list[int] = Field(default_factory=list)


class VoiceStats(BaseModel):
    total_voices: int
    global_voices: int
    user_voices: int
    active_voices: int
    updated_at: datetime
