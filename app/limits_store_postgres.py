from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Float, Index, Integer, and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_usage() -> dict[str, Any]:
    return {
        "requests_count": 0,
        "total_characters": 0,
        "total_duration_sec": 0.0,
        "successful_requests": 0,
        "failed_requests": 0,
    }


class Base(DeclarativeBase):
    pass


class UserLimitsRow(Base):
    __tablename__ = "tts_user_limits"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    max_text_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tts_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (Index("ix_tts_user_limits_updated_at", updated_at),)


class UsageDailyRow(Base):
    __tablename__ = "tts_usage_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    requests_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_characters: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_duration_sec: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    successful_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        Index("ix_tts_usage_daily_user_day", user_id, day),
        Index("ix_tts_usage_daily_day", day),
    )


class PostgresTTSLimitsStore:
    def __init__(
        self,
        database_url: str,
        *,
        default_max_text_length: int,
        default_daily_limit: int,
        default_priority_level: int,
        default_tts_enabled: bool,
        retention_days: int,
        echo: bool = False,
    ) -> None:
        normalized = database_url.strip()
        if normalized.startswith("postgresql://"):
            normalized = normalized.replace("postgresql://", "postgresql+asyncpg://", 1)
        if normalized.startswith("postgres://"):
            normalized = normalized.replace("postgres://", "postgresql+asyncpg://", 1)
        if not normalized.startswith("postgresql+asyncpg://"):
            raise ValueError("F5_TTS_DATABASE_URL must use PostgreSQL (postgresql://...)")

        self.engine = create_async_engine(normalized, echo=echo, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)

        self.default_max_text_length = max(10, int(default_max_text_length))
        self.default_daily_limit = max(1, int(default_daily_limit))
        self.default_priority_level = max(1, int(default_priority_level))
        self.default_tts_enabled = bool(default_tts_enabled)
        self.retention_days = max(2, int(retention_days))

    async def startup(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()

    async def get_user_limits(self, user_id: int) -> dict[str, Any]:
        async with self.session_factory() as session:
            row = await session.get(UserLimitsRow, int(user_id))
            limits = self._default_limits()
            if row is not None:
                if row.max_text_length is not None:
                    limits["max_text_length"] = int(row.max_text_length)
                if row.daily_limit is not None:
                    limits["daily_limit"] = int(row.daily_limit)
                if row.priority_level is not None:
                    limits["priority_level"] = int(row.priority_level)
                if row.tts_enabled is not None:
                    limits["tts_enabled"] = bool(row.tts_enabled)
            return limits

    async def update_user_limits(self, user_id: int, patch: dict[str, Any]) -> dict[str, Any]:
        sanitized = self._sanitize_limits_patch(patch)
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(UserLimitsRow, int(user_id))
                if row is None:
                    row = UserLimitsRow(user_id=int(user_id))
                    session.add(row)
                for key, value in sanitized.items():
                    setattr(row, key, value)
                row.updated_at = datetime.now(timezone.utc)
                await self._prune_usage(session)
        return await self.get_user_limits(user_id)

    async def validate_request(self, user_id: int, text: str) -> tuple[bool, str, dict[str, Any], dict[str, Any]]:
        limits = await self.get_user_limits(user_id)
        usage = await self.get_daily_usage(user_id, datetime.now(timezone.utc).date())
        text_len = len(text or "")

        if not limits["tts_enabled"]:
            return False, "TTS is disabled for this user", limits, usage
        if text_len > int(limits["max_text_length"]):
            return (
                False,
                f"Text too long. Maximum {limits['max_text_length']}, got {text_len}",
                limits,
                usage,
            )
        if int(usage["requests_count"]) >= int(limits["daily_limit"]):
            return (
                False,
                f"Daily request limit exceeded. Limit {limits['daily_limit']}, used {usage['requests_count']}",
                limits,
                usage,
            )
        return True, "Request allowed", limits, usage

    async def log_request(
        self,
        user_id: int,
        *,
        text_length: int,
        duration_sec: float | None,
        success: bool,
    ) -> None:
        today = datetime.now(timezone.utc).date()
        uid = int(user_id)
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(UsageDailyRow, {"day": today, "user_id": uid})
                if row is None:
                    row = UsageDailyRow(day=today, user_id=uid)
                    session.add(row)

                row.requests_count = int(row.requests_count or 0) + 1
                row.total_characters = int(row.total_characters or 0) + max(0, int(text_length))
                row.total_duration_sec = float(row.total_duration_sec or 0.0) + max(0.0, float(duration_sec or 0.0))
                if success:
                    row.successful_requests = int(row.successful_requests or 0) + 1
                else:
                    row.failed_requests = int(row.failed_requests or 0) + 1
                row.updated_at = datetime.now(timezone.utc)
                await self._prune_usage(session)

    async def get_daily_usage(self, user_id: int, target_date: date) -> dict[str, Any]:
        async with self.session_factory() as session:
            row = await session.get(UsageDailyRow, {"day": target_date, "user_id": int(user_id)})
            if row is None:
                return _empty_usage()
            return self._usage_from_row(row)

    async def get_user_stats(self, user_id: int, days: int = 7) -> dict[str, Any]:
        span = max(1, int(days))
        threshold = datetime.now(timezone.utc).date() - timedelta(days=span - 1)
        async with self.session_factory() as session:
            stmt = select(
                func.coalesce(func.sum(UsageDailyRow.requests_count), 0),
                func.coalesce(func.sum(UsageDailyRow.total_characters), 0),
                func.coalesce(func.sum(UsageDailyRow.total_duration_sec), 0.0),
                func.coalesce(func.sum(UsageDailyRow.successful_requests), 0),
                func.coalesce(func.sum(UsageDailyRow.failed_requests), 0),
            ).where(
                and_(
                    UsageDailyRow.user_id == int(user_id),
                    UsageDailyRow.day >= threshold,
                )
            )
            row = (await session.execute(stmt)).one()

        total = {
            "requests_count": int(row[0]),
            "total_characters": int(row[1]),
            "total_duration_sec": float(row[2]),
            "successful_requests": int(row[3]),
            "failed_requests": int(row[4]),
        }
        requests_count = int(total["requests_count"])
        success = int(total["successful_requests"])
        success_rate = (success / requests_count * 100.0) if requests_count else 0.0
        avg_duration = (float(total["total_duration_sec"]) / requests_count) if requests_count else 0.0

        return {
            "period_days": span,
            "user_id": int(user_id),
            **total,
            "success_rate": round(success_rate, 2),
            "avg_duration_sec": round(avg_duration, 4),
        }

    async def get_global_stats(self, days: int = 7) -> dict[str, Any]:
        span = max(1, int(days))
        threshold = datetime.now(timezone.utc).date() - timedelta(days=span - 1)
        async with self.session_factory() as session:
            stmt = select(
                func.coalesce(func.count(func.distinct(UsageDailyRow.user_id)), 0),
                func.coalesce(func.sum(UsageDailyRow.requests_count), 0),
                func.coalesce(func.sum(UsageDailyRow.total_characters), 0),
                func.coalesce(func.sum(UsageDailyRow.total_duration_sec), 0.0),
                func.coalesce(func.sum(UsageDailyRow.successful_requests), 0),
                func.coalesce(func.sum(UsageDailyRow.failed_requests), 0),
            ).where(UsageDailyRow.day >= threshold)
            row = (await session.execute(stmt)).one()

        unique_users = int(row[0])
        total = {
            "requests_count": int(row[1]),
            "total_characters": int(row[2]),
            "total_duration_sec": float(row[3]),
            "successful_requests": int(row[4]),
            "failed_requests": int(row[5]),
        }
        requests_count = int(total["requests_count"])
        success = int(total["successful_requests"])
        success_rate = (success / requests_count * 100.0) if requests_count else 0.0
        avg_requests = (requests_count / unique_users) if unique_users else 0.0

        return {
            "period_days": span,
            "unique_users": unique_users,
            **total,
            "success_rate": round(success_rate, 2),
            "avg_requests_per_user": round(avg_requests, 3),
        }

    async def _prune_usage(self, session: AsyncSession) -> None:
        threshold = datetime.now(timezone.utc).date() - timedelta(days=self.retention_days)
        await session.execute(delete(UsageDailyRow).where(UsageDailyRow.day < threshold))

    def _default_limits(self) -> dict[str, Any]:
        return {
            "max_text_length": self.default_max_text_length,
            "daily_limit": self.default_daily_limit,
            "priority_level": self.default_priority_level,
            "tts_enabled": self.default_tts_enabled,
        }

    @staticmethod
    def _sanitize_limits_patch(patch: dict[str, Any]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        if "max_text_length" in patch:
            output["max_text_length"] = max(10, min(5000, int(patch["max_text_length"])))
        if "daily_limit" in patch:
            output["daily_limit"] = max(1, min(10000, int(patch["daily_limit"])))
        if "priority_level" in patch:
            output["priority_level"] = max(1, min(10, int(patch["priority_level"])))
        if "tts_enabled" in patch:
            output["tts_enabled"] = bool(patch["tts_enabled"])
        return output

    @staticmethod
    def _usage_from_row(row: UsageDailyRow) -> dict[str, Any]:
        return {
            "requests_count": int(row.requests_count or 0),
            "total_characters": int(row.total_characters or 0),
            "total_duration_sec": float(row.total_duration_sec or 0.0),
            "successful_requests": int(row.successful_requests or 0),
            "failed_requests": int(row.failed_requests or 0),
        }
