#!/usr/bin/env python3
"""Ensure `voices.is_global` column exists for PostgreSQL-based F5_tts DB."""

from __future__ import annotations

from sqlalchemy import inspect, text

from database import engine


def migrate() -> int:
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("voices")}

    if "is_global" in columns:
        print("[OK] Column voices.is_global already exists")
        return 0

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE voices ADD COLUMN is_global BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("UPDATE voices SET is_global = TRUE WHERE owner_id IS NULL"))
        conn.execute(text("UPDATE voices SET is_global = FALSE WHERE owner_id IS NOT NULL"))

    print("[OK] Added voices.is_global and backfilled existing rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(migrate())
