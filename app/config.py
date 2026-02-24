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

    engine_mode: str = Field("mock", alias="F5_TTS_ENGINE_MODE")
    upstream_dir: str = Field("vendor/F5-TTS", alias="F5_TTS_UPSTREAM_DIR")
    russian_weights_dir: str = Field("models/F5-TTS_RUSSIAN", alias="F5_TTS_RUSSIAN_WEIGHTS_DIR")
    enable_prewarm: bool = Field(True, alias="F5_TTS_ENABLE_PREWARM")

    audio_dir: str = Field("data/audio", alias="F5_TTS_AUDIO_DIR")
    voices_state_file: str = Field("data/voices/state.json", alias="F5_TTS_VOICES_STATE_FILE")

    ru_yo_dict_file: str = Field("app/data/yo_words.json", alias="F5_TTS_RU_YO_DICT_FILE")
    ru_accents_file: str = Field("app/data/accents.json", alias="F5_TTS_RU_ACCENTS_FILE")

    provider_timeout_sec: float = Field(15.0, alias="F5_TTS_PROVIDER_TIMEOUT_SEC")

    @property
    def api_keys(self) -> set[str]:
        return {item.strip() for item in self.api_keys_raw.split(",") if item.strip()}

    @property
    def audio_path(self) -> Path:
        return Path(self.audio_dir).resolve()

    @property
    def voices_state_path(self) -> Path:
        return Path(self.voices_state_file).resolve()

    @property
    def ru_yo_dict_path(self) -> Path:
        return Path(self.ru_yo_dict_file).resolve()

    @property
    def ru_accents_path(self) -> Path:
        return Path(self.ru_accents_file).resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

