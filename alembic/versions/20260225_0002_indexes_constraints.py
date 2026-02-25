"""add indexes and uniqueness constraints

Revision ID: 20260225_0002
Revises: 20260225_0001
Create Date: 2026-02-25 17:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260225_0002"
down_revision = "20260225_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_voices_name_lower ON voices ((lower(name)))"))
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_voices_global_lower_name "
            "ON voices ((lower(name))) WHERE voice_type = 'global'"
        )
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_voices_owner_lower_name "
            "ON voices (owner_id, (lower(name))) WHERE voice_type <> 'global'"
        )
    )
    op.create_index("ix_tts_user_limits_updated_at", "tts_user_limits", ["updated_at"], unique=False)
    op.create_index("ix_tts_usage_daily_user_day", "tts_usage_daily", ["user_id", "day"], unique=False)
    op.create_index("ix_tts_usage_daily_day", "tts_usage_daily", ["day"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tts_usage_daily_day", table_name="tts_usage_daily")
    op.drop_index("ix_tts_usage_daily_user_day", table_name="tts_usage_daily")
    op.drop_index("ix_tts_user_limits_updated_at", table_name="tts_user_limits")
    op.drop_index("ux_voices_owner_lower_name", table_name="voices")
    op.drop_index("ux_voices_global_lower_name", table_name="voices")
    op.drop_index("ix_voices_name_lower", table_name="voices")
