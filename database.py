import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger(__name__)

PLACEHOLDER_DATABASE_URL = "postgresql://user:password@localhost:5432/f5_tts_db"


def _clean_env_value(value: str | None) -> str:
    if value is None:
        return ""
    # Drop quotes and invisible whitespace often introduced by copy/paste.
    return value.strip().strip('"').strip("'").replace("\ufeff", "").replace("\u00a0", "").strip()


def _resolve_database_url() -> str:
    env_database_url = _clean_env_value(os.getenv("DATABASE_URL"))
    if env_database_url and env_database_url != PLACEHOLDER_DATABASE_URL:
        return env_database_url

    if not env_database_url:
        logger.warning(
            "[DB] DATABASE_URL is not set in F5_tts/.env. "
            "Using placeholder value; set DATABASE_URL explicitly for real runs."
        )
        return PLACEHOLDER_DATABASE_URL

    logger.warning(
        "[DB] DATABASE_URL in F5_tts/.env uses placeholder value. "
        "Set DATABASE_URL explicitly before production run."
    )
    return env_database_url


DATABASE_URL = _resolve_database_url()

IS_TESTING = os.getenv("TESTING", "false").lower() == "true"
IS_POSTGRESQL = DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgresql+psycopg2://")
if not IS_POSTGRESQL and not IS_TESTING:
    raise ValueError(f"Only PostgreSQL is supported. Current DATABASE_URL: {DATABASE_URL[:50]}...")

if IS_TESTING:
    engine = create_engine(DATABASE_URL)
else:
    engine = create_engine(
        DATABASE_URL,
        pool_size=20,
        max_overflow=30,
        pool_timeout=60,
        pool_recycle=3600,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 10,
            "application_name": "f5_tts",
            "options": "-c statement_timeout=30000",
        },
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Keep model fields aligned with bot_service.database where shared.
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, ForeignKey, Float, UniqueConstraint
from sqlalchemy.sql import func


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    avatar = Column(String, nullable=True)
    platform = Column(String, default="twitch")
    twitch_access_token = Column(String, nullable=True)
    twitch_refresh_token = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False)
    settings = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), default=func.now())

    # Per-user TTS limits and controls.
    tts_max_text_length = Column(Integer, default=200)
    tts_daily_limit = Column(Integer, default=100)
    tts_gpu_time_limit = Column(Float, default=300.0)
    tts_priority_level = Column(Integer, default=2)
    tts_enabled = Column(Boolean, default=True)


class Voice(Base):
    __tablename__ = "voices"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    voice_type = Column(String, default="global")  # "global" or "user"
    file_path = Column(String, nullable=False)
    reference_text = Column(String, nullable=True)  # Legacy replacement for ref_text_path.
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_public = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    is_global = Column(Boolean, default=False)  # True for admin-uploaded global voices, False for user voices.
    created_at = Column(DateTime(timezone=True), default=func.now())

    # Runtime generation settings (user-tunable).
    cfg_strength = Column(Float, default=2.5)
    speed_preset = Column(String, default="normal")  # "very_slow", "slow", "normal"

    # Dynamic parameters are controlled in runtime code and are not persisted in DB:
    # target_rms, speed, nfe_step.

    # Fixed parameters (not user-tunable).
    cross_fade_duration = Column(Float, default=0.15)
    silence_duration_ms = Column(Integer, default=100)
    sway_sampling_coef = Column(Float, default=-1.0)


class UserVoiceEnabled(Base):
    """Stores whether a specific voice is enabled for a user."""

    __tablename__ = "user_voice_enabled"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    voice_id = Column(Integer, ForeignKey("voices.id"), nullable=False, index=True)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # One user - one voice toggle row.
    __table_args__ = (
        UniqueConstraint("user_id", "voice_id", name="uq_user_voice"),
    )


class UserTTSUsage(Base):
    """Tracks per-user TTS usage for billing and throttling."""

    __tablename__ = "user_tts_usage"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(DateTime(timezone=True), default=func.now(), index=True)

    # Usage counters.
    requests_count = Column(Integer, default=0)
    gpu_time_seconds = Column(Float, default=0.0)
    cpu_time_seconds = Column(Float, default=0.0)
    total_characters = Column(Integer, default=0)
    successful_requests = Column(Integer, default=0)
    failed_requests = Column(Integer, default=0)

    # Resource split.
    gpu_requests = Column(Integer, default=0)
    cpu_requests = Column(Integer, default=0)

    # Priority split.
    critical_requests = Column(Integer, default=0)
    high_requests = Column(Integer, default=0)
    normal_requests = Column(Integer, default=0)
    low_requests = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        raise e
    finally:
        try:
            db.close()
        except Exception:
            pass  # Ignore close errors during shutdown.


def close_all_connections():
    """Closes all active SQLAlchemy connections."""

    try:
        engine.dispose()
    except Exception:
        pass


def init_db():
    """Initializes database schema."""

    # Create all tables.
    try:
        Base.metadata.create_all(bind=engine)
    except UnicodeDecodeError as exc:
        logger.error(
            "[DB] PostgreSQL connection failed while decoding server response. Check DATABASE_URL in F5_tts/.env."
        )
        raise RuntimeError(
            "PostgreSQL connection failed due to invalid DATABASE_URL or unreachable PostgreSQL server."
        ) from exc
