"""init tts schema

Revision ID: 20260225_0001
Revises:
Create Date: 2026-02-25 16:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260225_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("voice_type", sa.String(length=16), nullable=False, server_default="global"),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("reference_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
        sa.Column("cfg_strength", sa.Float(), nullable=True),
        sa.Column("speed_preset", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_voices_voice_type", "voices", ["voice_type"], unique=False)
    op.create_index("ix_voices_owner_id", "voices", ["owner_id"], unique=False)
    op.create_index("ix_voices_is_active", "voices", ["is_active"], unique=False)

    op.create_table(
        "user_voice_enabled",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("voice_id", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["voice_id"], ["voices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "voice_id"),
    )

    op.create_table(
        "tts_user_limits",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("max_text_length", sa.Integer(), nullable=True),
        sa.Column("daily_limit", sa.Integer(), nullable=True),
        sa.Column("priority_level", sa.Integer(), nullable=True),
        sa.Column("tts_enabled", sa.Boolean(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "tts_usage_daily",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("requests_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_characters", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_duration_sec", sa.Float(), nullable=False, server_default="0"),
        sa.Column("successful_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("day", "user_id"),
    )


def downgrade() -> None:
    op.drop_table("tts_usage_daily")
    op.drop_table("tts_user_limits")
    op.drop_table("user_voice_enabled")
    op.drop_index("ix_voices_is_active", table_name="voices")
    op.drop_index("ix_voices_owner_id", table_name="voices")
    op.drop_index("ix_voices_voice_type", table_name="voices")
    op.drop_table("voices")
