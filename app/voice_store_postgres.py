from __future__ import annotations

import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    and_,
    delete,
    func,
    or_,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .schemas import VoiceStats


class Base(DeclarativeBase):
    pass


class VoiceRow(Base):
    __tablename__ = "voices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    voice_type: Mapped[str] = mapped_column(String(16), nullable=False, default="global", index=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    reference_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cfg_strength: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_preset: Mapped[str | None] = mapped_column(String(32), nullable=True)
    __table_args__ = (
        Index("ix_voices_name_lower", func.lower(name)),
        Index(
            "ux_voices_global_lower_name",
            func.lower(name),
            unique=True,
            postgresql_where=text("voice_type = 'global'"),
        ),
        Index(
            "ux_voices_owner_lower_name",
            owner_id,
            func.lower(name),
            unique=True,
            postgresql_where=text("voice_type <> 'global'"),
        ),
    )


class UserVoiceEnabledRow(Base):
    __tablename__ = "user_voice_enabled"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    voice_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("voices.id", ondelete="CASCADE"),
        primary_key=True,
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


def _to_utc_iso(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat()


class PostgresVoiceStore:
    def __init__(self, database_url: str, voices_dir: Path, *, echo: bool = False) -> None:
        normalized = database_url.strip()
        if normalized.startswith("postgresql://"):
            normalized = normalized.replace("postgresql://", "postgresql+asyncpg://", 1)
        if normalized.startswith("postgres://"):
            normalized = normalized.replace("postgres://", "postgresql+asyncpg://", 1)
        if not normalized.startswith("postgresql+asyncpg://"):
            raise ValueError("F5_TTS_DATABASE_URL must use PostgreSQL (postgresql://...)")

        self.voices_dir = voices_dir
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        self.engine = create_async_engine(normalized, echo=echo, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)

    async def startup(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await self._ensure_default_voice()

    async def close(self) -> None:
        await self.engine.dispose()

    async def list_global_voices(self) -> list[dict[str, Any]]:
        async with self.session_factory() as session:
            stmt = (
                select(VoiceRow)
                .where(and_(VoiceRow.voice_type == "global", VoiceRow.is_active.is_(True)))
                .order_by(VoiceRow.id.asc())
            )
            rows = (await session.scalars(stmt)).all()
            return [self._row_to_dict(row) for row in rows]

    async def list_available_voices(self, user_id: int | None) -> list[dict[str, Any]]:
        return await self._active_voices_for_user(user_id)

    async def list_user_voices(self, user_id: int) -> list[dict[str, Any]]:
        async with self.session_factory() as session:
            stmt = (
                select(VoiceRow)
                .where(
                    and_(
                        VoiceRow.owner_id == int(user_id),
                        VoiceRow.voice_type != "global",
                        VoiceRow.is_active.is_(True),
                    )
                )
                .order_by(VoiceRow.id.asc())
            )
            rows = (await session.scalars(stmt)).all()
            return [self._row_to_dict(row) for row in rows]

    async def list_all_voices(self) -> list[dict[str, Any]]:
        async with self.session_factory() as session:
            stmt = select(VoiceRow).order_by(VoiceRow.id.asc())
            rows = (await session.scalars(stmt)).all()
            return [self._row_to_dict(row) for row in rows]

    async def get_voice_by_id(self, voice_id: int) -> dict[str, Any] | None:
        async with self.session_factory() as session:
            row = await session.get(VoiceRow, int(voice_id))
            if not row:
                return None
            return self._row_to_dict(row)

    async def get_voice_by_name(self, name: str) -> dict[str, Any] | None:
        normalized = name.strip().lower()
        if not normalized:
            return None
        async with self.session_factory() as session:
            stmt = select(VoiceRow).where(func.lower(VoiceRow.name) == normalized).order_by(VoiceRow.id.asc()).limit(1)
            row = await session.scalar(stmt)
            if not row:
                return None
            return self._row_to_dict(row)

    async def create_voice(
        self,
        *,
        name: str,
        owner_id: int | None,
        voice_type: str,
        file_path: str,
        is_public: bool,
        reference_text: str | None = None,
        cfg_strength: float | None = None,
        speed_preset: str | None = None,
    ) -> dict[str, Any]:
        normalized_name = name.strip().lower()
        normalized_type = (voice_type or "user").strip().lower()
        owner = int(owner_id) if owner_id is not None else None
        async with self.session_factory() as session:
            async with session.begin():
                if normalized_type == "global":
                    dup_stmt = select(VoiceRow.id).where(func.lower(VoiceRow.name) == normalized_name)
                else:
                    dup_stmt = select(VoiceRow.id).where(
                        and_(
                            func.lower(VoiceRow.name) == normalized_name,
                            or_(
                                VoiceRow.voice_type == "global",
                                and_(
                                    VoiceRow.voice_type != "global",
                                    VoiceRow.owner_id == owner,
                                ),
                            ),
                        )
                    )
                duplicate = await session.scalar(dup_stmt)
                if duplicate is not None:
                    raise ValueError(f"Voice '{name}' already exists")

                row = VoiceRow(
                    name=name,
                    file_path=file_path,
                    voice_type=normalized_type,
                    owner_id=owner,
                    is_public=bool(is_public),
                    is_active=True,
                    reference_text=reference_text,
                    cfg_strength=cfg_strength,
                    speed_preset=speed_preset,
                )
                session.add(row)
                await session.flush()
                await session.refresh(row)
                return self._row_to_dict(row)

    async def update_voice_settings(self, voice_id: int, patch: dict[str, Any]) -> dict[str, Any] | None:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(VoiceRow, int(voice_id))
                if not row:
                    return None
                for key in ("reference_text", "cfg_strength", "speed_preset"):
                    if key in patch:
                        setattr(row, key, patch[key])
                await session.flush()
                await session.refresh(row)
                return self._row_to_dict(row)

    async def rename_voice(self, voice_id: int, new_name: str) -> dict[str, Any] | None:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(VoiceRow, int(voice_id))
                if not row:
                    return None
                normalized_name = new_name.strip().lower()
                if row.voice_type == "global":
                    dup_stmt = select(VoiceRow.id).where(
                        and_(
                            VoiceRow.id != row.id,
                            func.lower(VoiceRow.name) == normalized_name,
                        )
                    )
                else:
                    dup_stmt = select(VoiceRow.id).where(
                        and_(
                            VoiceRow.id != row.id,
                            func.lower(VoiceRow.name) == normalized_name,
                            or_(
                                VoiceRow.voice_type == "global",
                                and_(
                                    VoiceRow.voice_type != "global",
                                    VoiceRow.owner_id == row.owner_id,
                                ),
                            ),
                        )
                    )
                duplicate = await session.scalar(dup_stmt)
                if duplicate is not None:
                    raise ValueError(f"Voice '{new_name}' already exists")
                row.name = new_name
                await session.flush()
                await session.refresh(row)
                return self._row_to_dict(row)

    async def toggle_voice(self, voice_id: int) -> dict[str, Any] | None:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(VoiceRow, int(voice_id))
                if not row:
                    return None
                row.is_active = not bool(row.is_active)
                await session.flush()
                await session.refresh(row)
                return self._row_to_dict(row)

    async def delete_voice(self, voice_id: int) -> bool:
        async with self.session_factory() as session:
            async with session.begin():
                result = await session.execute(delete(VoiceRow).where(VoiceRow.id == int(voice_id)))
                return bool((result.rowcount or 0) > 0)

    async def get_enabled_voice_ids(self, user_id: int) -> list[int]:
        async with self.session_factory() as session:
            stmt = (
                select(UserVoiceEnabledRow.voice_id)
                .join(VoiceRow, VoiceRow.id == UserVoiceEnabledRow.voice_id)
                .where(
                    and_(
                        UserVoiceEnabledRow.user_id == int(user_id),
                        UserVoiceEnabledRow.is_enabled.is_(True),
                        VoiceRow.is_active.is_(True),
                    )
                )
                .order_by(UserVoiceEnabledRow.voice_id.asc())
            )
            rows = (await session.scalars(stmt)).all()
            return [int(item) for item in rows]

    async def set_enabled_voice_ids(self, user_id: int, voice_ids: list[int]) -> list[int]:
        async with self.session_factory() as session:
            async with session.begin():
                valid_ids = set((await session.scalars(select(VoiceRow.id))).all())
                filtered = sorted({int(item) for item in voice_ids if int(item) in valid_ids})
                await session.execute(delete(UserVoiceEnabledRow).where(UserVoiceEnabledRow.user_id == int(user_id)))
                for voice_id in filtered:
                    session.add(UserVoiceEnabledRow(user_id=int(user_id), voice_id=int(voice_id), is_enabled=True))
                return filtered

    async def toggle_enabled_voice_id(self, user_id: int, voice_id: int, is_enabled: bool) -> list[int]:
        user = int(user_id)
        voice = int(voice_id)
        async with self.session_factory() as session:
            async with session.begin():
                exists_stmt = select(VoiceRow.id).where(VoiceRow.id == voice)
                exists = await session.scalar(exists_stmt)
                if exists is None:
                    return await self.get_enabled_voice_ids(user)

                if is_enabled:
                    row_stmt = select(UserVoiceEnabledRow).where(
                        and_(
                            UserVoiceEnabledRow.user_id == user,
                            UserVoiceEnabledRow.voice_id == voice,
                        )
                    )
                    row = await session.scalar(row_stmt)
                    if row is None:
                        session.add(UserVoiceEnabledRow(user_id=user, voice_id=voice, is_enabled=True))
                    else:
                        row.is_enabled = True
                else:
                    await session.execute(
                        delete(UserVoiceEnabledRow).where(
                            and_(
                                UserVoiceEnabledRow.user_id == user,
                                UserVoiceEnabledRow.voice_id == voice,
                            )
                        )
                    )
            return await self.get_enabled_voice_ids(user)

    async def resolve_voice_for_user(self, user_id: int | None, requested_voice: str | None) -> str:
        selected = await self.resolve_voice_record_for_user(user_id, requested_voice)
        if not selected:
            return "female_1"
        return str(selected["name"])

    async def resolve_voice_record_for_user(
        self,
        user_id: int | None,
        requested_voice: str | None,
    ) -> dict[str, Any] | None:
        active = await self._active_voices_for_user(user_id)
        if not active:
            return None
        enabled_pool = await self._filter_by_enabled(user_id, active)
        effective_pool = enabled_pool if enabled_pool else active
        requested = (requested_voice or "").strip()
        if requested and requested.lower() != "random":
            matched = self._find_by_name(effective_pool, requested)
            if matched:
                return matched
        return random.choice(effective_pool)

    async def stats(self) -> VoiceStats:
        async with self.session_factory() as session:
            total = int((await session.scalar(select(func.count()).select_from(VoiceRow))) or 0)
            global_count = int(
                (
                    await session.scalar(
                        select(func.count()).select_from(VoiceRow).where(VoiceRow.voice_type == "global")
                    )
                )
                or 0
            )
            user_count = int(
                (
                    await session.scalar(
                        select(func.count()).select_from(VoiceRow).where(VoiceRow.voice_type != "global")
                    )
                )
                or 0
            )
            active_count = int(
                (
                    await session.scalar(
                        select(func.count()).select_from(VoiceRow).where(VoiceRow.is_active.is_(True))
                    )
                )
                or 0
            )
        return VoiceStats(
            total_voices=total,
            global_voices=global_count,
            user_voices=user_count,
            active_voices=active_count,
            updated_at=datetime.now(timezone.utc),
        )

    async def _ensure_default_voice(self) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                stmt = select(VoiceRow.id).where(
                    and_(
                        VoiceRow.voice_type == "global",
                        func.lower(VoiceRow.name) == "female_1",
                    )
                )
                exists = await session.scalar(stmt)
                if exists is None:
                    session.add(
                        VoiceRow(
                            name="female_1",
                            file_path="",
                            voice_type="global",
                            owner_id=None,
                            is_public=True,
                            is_active=True,
                            reference_text=None,
                            cfg_strength=None,
                            speed_preset=None,
                        )
                    )

    async def _active_voices_for_user(self, user_id: int | None) -> list[dict[str, Any]]:
        async with self.session_factory() as session:
            if user_id is None:
                stmt = (
                    select(VoiceRow)
                    .where(and_(VoiceRow.is_active.is_(True), VoiceRow.voice_type == "global"))
                    .order_by(VoiceRow.id.asc())
                )
            else:
                stmt = (
                    select(VoiceRow)
                    .where(
                        and_(
                            VoiceRow.is_active.is_(True),
                            or_(
                                VoiceRow.voice_type == "global",
                                VoiceRow.owner_id == int(user_id),
                            ),
                        )
                    )
                    .order_by(VoiceRow.id.asc())
                )
            rows = (await session.scalars(stmt)).all()
            return [self._row_to_dict(row) for row in rows]

    async def _filter_by_enabled(self, user_id: int | None, voices: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if user_id is None:
            return voices
        enabled_ids = set(await self.get_enabled_voice_ids(int(user_id)))
        if not enabled_ids:
            return voices
        return [voice for voice in voices if int(voice["id"]) in enabled_ids]

    @staticmethod
    def _find_by_name(voices: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
        lowered = name.strip().lower()
        for voice in voices:
            if str(voice.get("name", "")).strip().lower() == lowered:
                return voice
        return None

    @staticmethod
    def _row_to_dict(row: VoiceRow) -> dict[str, Any]:
        return {
            "id": int(row.id),
            "name": str(row.name),
            "file_path": str(row.file_path or ""),
            "voice_type": str(row.voice_type),
            "owner_id": int(row.owner_id) if row.owner_id is not None else None,
            "is_public": bool(row.is_public),
            "is_active": bool(row.is_active),
            "reference_text": row.reference_text,
            "created_at": _to_utc_iso(row.created_at),
            "cfg_strength": float(row.cfg_strength) if row.cfg_strength is not None else None,
            "speed_preset": row.speed_preset,
            "enabled_user_ids": [],
        }
