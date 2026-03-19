"""multi user auth

Revision ID: 20260319_0002
Revises: 20260318_0001
Create Date: 2026-03-19 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260319_0002"
down_revision = "20260318_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)

    op.create_table(
        "user_api_tokens",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("token_prefix", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_user_api_tokens_user_id", "user_api_tokens", ["user_id"], unique=False)
    op.create_index("ix_user_api_tokens_token_hash", "user_api_tokens", ["token_hash"], unique=False)

    op.create_table(
        "user_web_sessions",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("session_token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("session_token_hash"),
    )
    op.create_index("ix_user_web_sessions_user_id", "user_web_sessions", ["user_id"], unique=False)
    op.create_index("ix_user_web_sessions_session_token_hash", "user_web_sessions", ["session_token_hash"], unique=False)

    with op.batch_alter_table("queries") as batch_op:
        batch_op.add_column(sa.Column("owner_user_id", sa.String(length=32), nullable=True))
        batch_op.create_foreign_key(
            "fk_queries_owner_user_id_users",
            "users",
            ["owner_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_queries_owner_user_id", ["owner_user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("queries") as batch_op:
        batch_op.drop_index("ix_queries_owner_user_id")
        batch_op.drop_constraint("fk_queries_owner_user_id_users", type_="foreignkey")
        batch_op.drop_column("owner_user_id")

    op.drop_index("ix_user_web_sessions_session_token_hash", table_name="user_web_sessions")
    op.drop_index("ix_user_web_sessions_user_id", table_name="user_web_sessions")
    op.drop_table("user_web_sessions")

    op.drop_index("ix_user_api_tokens_token_hash", table_name="user_api_tokens")
    op.drop_index("ix_user_api_tokens_user_id", table_name="user_api_tokens")
    op.drop_table("user_api_tokens")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
