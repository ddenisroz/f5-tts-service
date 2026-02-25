from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_host: str = Field("0.0.0.0", alias="F5_TTS_SERVICE_HOST")
    service_port: int = Field(8011, alias="F5_TTS_SERVICE_PORT")
    public_base_url: str = Field("http://localhost:8011", alias="F5_TTS_SERVICE_PUBLIC_BASE_URL")
    api_keys_raw: str = Field("", alias="F5_TTS_SERVICE_API_KEYS")
    base_dir: str = Field(".", alias="F5_TTS_BASE_DIR")
    database_url: str = Field("", alias="F5_TTS_DATABASE_URL")
    database_echo: bool = Field(False, alias="F5_TTS_DATABASE_ECHO")

    engine_mode: str = Field("real", alias="F5_TTS_ENGINE_MODE")
    upstream_dir: str = Field("vendor/F5-TTS", alias="F5_TTS_UPSTREAM_DIR")
    russian_weights_dir: str = Field("models/F5-TTS_RUSSIAN", alias="F5_TTS_RUSSIAN_WEIGHTS_DIR")
    enable_prewarm: bool = Field(True, alias="F5_TTS_ENABLE_PREWARM")
    model_name: str = Field("F5TTS_v1_Base", alias="F5_TTS_MODEL_NAME")
    checkpoint_file: str = Field("", alias="F5_TTS_CHECKPOINT_FILE")
    vocab_file: str = Field("", alias="F5_TTS_VOCAB_FILE")
    hf_cache_dir: str = Field("models/cache", alias="F5_TTS_HF_CACHE_DIR")
    device: str = Field("", alias="F5_TTS_DEVICE")
    ode_method: str = Field("euler", alias="F5_TTS_ODE_METHOD")
    use_ema: bool = Field(True, alias="F5_TTS_USE_EMA")
    target_rms: float = Field(0.1, alias="F5_TTS_TARGET_RMS")
    cross_fade_duration: float = Field(0.15, alias="F5_TTS_CROSS_FADE_DURATION")
    nfe_step: int = Field(32, alias="F5_TTS_NFE_STEP")
    sway_sampling_coef: float = Field(-1.0, alias="F5_TTS_SWAY_SAMPLING_COEF")
    f5_default_cfg_strength: float = Field(2.0, alias="F5_TTS_DEFAULT_CFG_STRENGTH")
    f5_default_speed_preset: str = Field("normal", alias="F5_TTS_DEFAULT_SPEED_PRESET")
    default_ref_audio_file: str = Field("data/voices/default_ref.wav", alias="F5_TTS_DEFAULT_REF_AUDIO_FILE")
    f5_default_ref_text: str = Field("", alias="F5_TTS_DEFAULT_REF_TEXT")
    voice_upload_sample_rate: int = Field(24000, alias="F5_TTS_VOICE_UPLOAD_SAMPLE_RATE")
    voice_upload_max_bytes: int = Field(15_000_000, alias="F5_TTS_VOICE_UPLOAD_MAX_BYTES")
    voice_upload_min_duration_sec: float = Field(0.5, alias="F5_TTS_VOICE_UPLOAD_MIN_DURATION_SEC")
    voice_upload_max_duration_sec: float = Field(30.0, alias="F5_TTS_VOICE_UPLOAD_MAX_DURATION_SEC")
    voices_dir: str = Field("data/voices", alias="F5_TTS_VOICES_DIR")

    audio_dir: str = Field("data/audio", alias="F5_TTS_AUDIO_DIR")
    voices_state_file: str = Field("data/voices/state.json", alias="F5_TTS_VOICES_STATE_FILE")
    limits_state_file: str = Field("data/limits/state.json", alias="F5_TTS_LIMITS_STATE_FILE")
    limits_enabled: bool = Field(True, alias="F5_TTS_LIMITS_ENABLED")
    limit_default_max_text_length: int = Field(200, alias="F5_TTS_LIMIT_DEFAULT_MAX_TEXT_LENGTH")
    limit_default_daily_requests: int = Field(100, alias="F5_TTS_LIMIT_DEFAULT_DAILY_REQUESTS")
    limit_default_priority_level: int = Field(2, alias="F5_TTS_LIMIT_DEFAULT_PRIORITY_LEVEL")
    limit_default_tts_enabled: bool = Field(True, alias="F5_TTS_LIMIT_DEFAULT_TTS_ENABLED")
    limits_retention_days: int = Field(31, alias="F5_TTS_LIMITS_RETENTION_DAYS")

    ru_yo_dict_file: str = Field("app/data/yo_words.json", alias="F5_TTS_RU_YO_DICT_FILE")
    ru_accents_file: str = Field("app/data/accents.json", alias="F5_TTS_RU_ACCENTS_FILE")
    transcriber_enabled: bool = Field(True, alias="F5_TTS_TRANSCRIBER_ENABLED")
    transcriber_preload: bool = Field(False, alias="F5_TTS_TRANSCRIBER_PRELOAD")
    transcriber_model: str = Field("turbo", alias="F5_TTS_TRANSCRIBER_MODEL")
    transcriber_device: str = Field("auto", alias="F5_TTS_TRANSCRIBER_DEVICE")
    transcriber_compute_type: str = Field("auto", alias="F5_TTS_TRANSCRIBER_COMPUTE_TYPE")
    transcriber_language: str = Field("ru", alias="F5_TTS_TRANSCRIBER_LANGUAGE")

    provider_timeout_sec: float = Field(15.0, alias="F5_TTS_PROVIDER_TIMEOUT_SEC")
    max_input_text_length: int = Field(2000, alias="F5_TTS_MAX_INPUT_TEXT_LENGTH")

    @property
    def api_keys(self) -> set[str]:
        return {item.strip() for item in self.api_keys_raw.split(",") if item.strip()}

    @property
    def base_path(self) -> Path:
        return Path(self.base_dir).resolve()

    def _resolve_path(self, value: str) -> Path:
        raw = (value or "").strip()
        candidate = Path(raw) if raw else Path(".")
        if candidate.is_absolute():
            return candidate.resolve()
        return (self.base_path / candidate).resolve()

    @property
    def audio_path(self) -> Path:
        return self._resolve_path(self.audio_dir)

    @property
    def voices_state_path(self) -> Path:
        return self._resolve_path(self.voices_state_file)

    @property
    def ru_yo_dict_path(self) -> Path:
        return self._resolve_path(self.ru_yo_dict_file)

    @property
    def ru_accents_path(self) -> Path:
        return self._resolve_path(self.ru_accents_file)

    @property
    def limits_state_path(self) -> Path:
        return self._resolve_path(self.limits_state_file)

    @property
    def default_ref_audio_path(self) -> Path:
        return self._resolve_path(self.default_ref_audio_file)

    @property
    def voices_dir_path(self) -> Path:
        return self._resolve_path(self.voices_dir)

    @property
    def hf_cache_path(self) -> Path:
        return self._resolve_path(self.hf_cache_dir)

    @property
    def upstream_path(self) -> Path:
        return self._resolve_path(self.upstream_dir)

    @property
    def russian_weights_path(self) -> Path:
        return self._resolve_path(self.russian_weights_dir)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
