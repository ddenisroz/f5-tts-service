import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables from .env
load_dotenv()


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = str(raw).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


class AppConfig(BaseModel):
    # General settings
    host: str = Field(default_factory=lambda: _env_str("TTS_HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: _env_int("TTS_PORT", 8001))
    debug: bool = Field(default_factory=lambda: _env_bool("TTS_DEBUG", True))

    # Paths
    base_dir: Path = Path(__file__).resolve().parent

    @property
    def audio_path(self) -> Path:
        return self.base_dir / "audio"

    @property
    def voices_path(self) -> Path:
        return self.audio_path / "voices"

    @property
    def global_voices_path(self) -> Path:
        return self.voices_path / "global"

    @property
    def user_voices_path(self) -> Path:
        return self.voices_path / "user"

    @property
    def temp_audio_path(self) -> Path:
        return self.audio_path / "temp"

    @property
    def test_audio_path(self) -> Path:
        return self.audio_path / "test"

    @property
    def production_audio_path(self) -> Path:
        return self.audio_path / "production"

    @property
    def cache_audio_path(self) -> Path:
        return self.audio_path / "cache"

    @property
    def user_configs_path(self) -> Path:
        return self.base_dir / "user_configs"

    # Logging and CORS
    log_level: str = Field(default_factory=lambda: _env_str("TTS_LOG_LEVEL", "INFO"))
    cors_origins: str = Field(
        default_factory=lambda: _env_str(
            "CORS_ORIGINS",
            "http://localhost:5173,http://localhost:3000,http://localhost:8000",
        )
    )
    log_file: Optional[str] = Field(default_factory=lambda: os.getenv("TTS_LOG_FILE"))

    # F5-TTS tunables
    cfg_strength: float = Field(default_factory=lambda: _env_float("TTS_CFG_STRENGTH", 2.5))

    # Fixed parameters
    target_rms: float = 0.1
    cross_fade_duration: float = 0.15
    silence_duration_ms: int = 100
    sway_sampling_coef: float = -1.0


# Singleton config
config = AppConfig()

# Ensure directories exist at import time
config.voices_path.mkdir(parents=True, exist_ok=True)
config.global_voices_path.mkdir(parents=True, exist_ok=True)
config.user_voices_path.mkdir(parents=True, exist_ok=True)
config.audio_path.mkdir(parents=True, exist_ok=True)
config.test_audio_path.mkdir(parents=True, exist_ok=True)
config.production_audio_path.mkdir(parents=True, exist_ok=True)
config.temp_audio_path.mkdir(parents=True, exist_ok=True)
config.user_configs_path.mkdir(parents=True, exist_ok=True)
