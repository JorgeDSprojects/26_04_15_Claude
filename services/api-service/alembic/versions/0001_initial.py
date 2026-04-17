"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE criticality_level AS ENUM ('standard', 'buffered', 'critical')")
    op.execute("CREATE TYPE signal_datatype AS ENUM ('float', 'int', 'bool', 'string', 'enum')")

    op.create_table(
        "asset_types",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column(
            "isa95_level",
            sa.Text,
            sa.CheckConstraint(
                "isa95_level IN ('enterprise','site','area','line','cell')",
                name="ck_asset_types_isa95_level",
            ),
            nullable=False,
        ),
        sa.Column("description", sa.Text),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.create_table(
        "assets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("parent_id", sa.Integer, sa.ForeignKey("assets.id", ondelete="RESTRICT")),
        sa.Column("asset_type_id", sa.Integer, sa.ForeignKey("asset_types.id"), nullable=False),
        sa.Column("code", sa.Text, nullable=False),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("path", sa.Text, nullable=False, unique=True),
        sa.Column(
            "metadata",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("parent_id", "code", name="uq_assets_parent_code"),
    )
    op.create_index("idx_assets_path", "assets", ["path"])
    op.create_index("idx_assets_parent", "assets", ["parent_id"])

    op.create_table(
        "signal_types",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("description", sa.Text),
    )

    op.create_table(
        "signals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "asset_id",
            sa.Integer,
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "signal_type_id",
            sa.Integer,
            sa.ForeignKey("signal_types.id"),
            nullable=False,
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("unit", sa.Text),
        sa.Column(
            "datatype",
            sa.Enum(
                "float", "int", "bool", "string", "enum",
                name="signal_datatype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "criticality",
            sa.Enum(
                "standard", "buffered", "critical",
                name="criticality_level",
                create_type=False,
            ),
            nullable=False,
            server_default="standard",
        ),
        sa.Column("topic", sa.Text, nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("protocol", sa.Text),
        sa.Column(
            "connection_config",
            sa.dialects.postgresql.JSONB,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("polling_interval_ms", sa.Integer),
        sa.Column("min_value", sa.Double),
        sa.Column("max_value", sa.Double),
        sa.Column("enum_values", sa.dialects.postgresql.JSONB),
        sa.Column(
            "metadata",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("asset_id", "name", name="uq_signals_asset_name"),
    )
    op.create_index("idx_signals_asset", "signals", ["asset_id"])
    op.create_index("idx_signals_topic", "signals", ["topic"])
    op.create_index(
        "idx_signals_enabled",
        "signals",
        ["enabled"],
        postgresql_where=sa.text("enabled = true"),
    )
    op.create_index("idx_signals_criticality", "signals", ["criticality"])


def downgrade() -> None:
    op.drop_table("signals")
    op.drop_table("signal_types")
    op.drop_table("assets")
    op.drop_table("asset_types")
    op.execute("DROP TYPE IF EXISTS signal_datatype")
    op.execute("DROP TYPE IF EXISTS criticality_level")
