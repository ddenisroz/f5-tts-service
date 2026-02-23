# F5_tts/models.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import datetime as dt

class VoiceSchema(BaseModel):
    id: int
    name: str
    file_path: str
    reference_text: Optional[str] = None
    voice_type: str
    owner_id: Optional[int] = None
    is_public: bool
    is_active: bool
    is_global: bool = False
    created_at: Optional[dt.datetime] = None
    
    # Настройки генерации TTS
    cfg_strength: float = 2.0
    speed_preset: str = 'normal'
    cross_fade_duration: float = 0.15
    silence_duration: float = 0.0
    temperature: float = 1.0
    top_p: float = 0.9
    top_k: int = 50
    repetition_penalty: float = 1.0
    length_penalty: float = 1.0
    early_stopping: bool = False

    class Config:
        from_attributes = True

class VoiceSettingsSchema(BaseModel):
    """Схема для обновления настроек голоса"""
    cfg_strength: Optional[float] = Field(None, ge=0.1, le=10.0, description="CFG strength (0.1-10.0)")
    speed_preset: Optional[str] = Field(None, pattern='^(very_slow|slow|normal|fast|very_fast)$', description="Speed preset")
    cross_fade_duration: Optional[float] = Field(None, ge=0.0, le=1.0, description="Cross fade duration in seconds")
    silence_duration: Optional[float] = Field(None, ge=0.0, le=2.0, description="Silence duration in seconds")
    temperature: Optional[float] = Field(None, ge=0.1, le=2.0, description="Temperature for sampling")
    top_p: Optional[float] = Field(None, ge=0.1, le=1.0, description="Top-p sampling")
    top_k: Optional[int] = Field(None, ge=1, le=100, description="Top-k sampling")
    repetition_penalty: Optional[float] = Field(None, ge=0.1, le=2.0, description="Repetition penalty")
    length_penalty: Optional[float] = Field(None, ge=0.1, le=2.0, description="Length penalty")
    early_stopping: Optional[bool] = Field(None, description="Early stopping")
    reference_text: Optional[str] = Field(None, min_length=1, max_length=5000, description="Reference text for voice synthesis")

class TtsConfigSchema(BaseModel):
    cfg_strength: float = Field(ge=0.1, le=10.0, description="CFG strength (0.1-10.0)")

class TtsConfigResponse(BaseModel):
    cfg_strength: float

class SynthesisRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000, description="Text to synthesize (1-1000 characters)")
    voice_name: str = Field(..., min_length=1, max_length=100, description="Voice name")
    user_id: Optional[int] = Field(None, ge=1, description="User ID")
    volume_level: Optional[float] = Field(50.0, ge=0.0, le=100.0, description="Volume level (0-100%)")
    cfg_strength: Optional[float] = Field(None, ge=0.1, le=10.0, description="CFG strength override")
    speed_preset: Optional[str] = Field(None, pattern='^(very_slow|slow|normal|fast|very_fast)$', description="Speed preset override")
    priority: Optional[int] = Field(2, ge=1, le=4, description="Priority level (1-4)")

class SynthesisResponse(BaseModel):
    success: bool
    message: str
    audio_file: Optional[str] = None
    audio_url: Optional[str] = None
    duration: Optional[float] = None

class VoiceUploadResponse(BaseModel):
    success: bool
    message: str
    voice_id: Optional[int] = None
    voice_name: Optional[str] = None

class TranscriptionResponse(BaseModel):
    success: bool
    text: Optional[str] = None
    message: str

class UserTTSLimitsSchema(BaseModel):
    """Схема настроек TTS пользователя"""
    max_text_length: int = Field(ge=10, le=1000, description="Maximum text length (10-1000 characters)")
    daily_limit: int = Field(ge=1, le=1000, description="Daily request limit (1-1000)")
    gpu_time_limit: float = Field(ge=10.0, le=3600.0, description="Daily GPU time limit in seconds (10-3600)")
    priority_level: int = Field(ge=1, le=4, description="Priority level (1-4)")
    tts_enabled: bool = Field(description="TTS enabled for user")

class UserTTSLimitsResponse(BaseModel):
    """Ответ с настройками TTS пользователя"""
    max_text_length: int
    daily_limit: int
    gpu_time_limit: float
    priority_level: int
    tts_enabled: bool
    current_usage: Optional[Dict[str, Any]] = None

class UserTTSUsageSchema(BaseModel):
    """Схема статистики использования TTS"""
    period_days: int
    total_requests: int
    total_gpu_time: float
    total_cpu_time: float
    total_characters: int
    successful_requests: int
    failed_requests: int
    gpu_requests: int
    cpu_requests: int
    success_rate: float
    avg_processing_time: float

class GlobalTTSStatsSchema(BaseModel):
    """Схема глобальной статистики TTS"""
    period_days: int
    unique_users: int
    total_requests: int
    total_gpu_time: float
    total_cpu_time: float
    total_characters: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    avg_requests_per_user: float

