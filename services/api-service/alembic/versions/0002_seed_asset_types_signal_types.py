"""seed asset_types and signal_types

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-17

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ASSET_TYPES = [
    ("enterprise", "enterprise", "Top-level enterprise"),
    ("wind_farm", "site", "Wind farm site"),
    ("sector", "area", "Wind farm sector/area"),
    ("wind_turbine", "line", "Individual wind turbine"),
    ("rotor", "cell", "Turbine rotor assembly"),
    ("nacelle", "cell", "Turbine nacelle"),
    ("generator", "cell", "Turbine generator"),
    ("gearbox", "cell", "Turbine gearbox"),
    ("tower", "cell", "Turbine tower"),
    ("controller", "cell", "Turbine controller / SCADA"),
]

SIGNAL_TYPES = [
    ("informative", "Real-time telemetry (measure)"),
    ("operational", "Events, alarms, state changes"),
    ("descriptive", "Static metadata ($meta)"),
    ("analytic", "Computed KPIs and predictions"),
]


def upgrade() -> None:
    for name, level, desc in ASSET_TYPES:
        op.execute(
            f"INSERT INTO asset_types (name, isa95_level, description) "
            f"VALUES ('{name}', '{level}', '{desc}')"
        )
    for name, desc in SIGNAL_TYPES:
        op.execute(
            f"INSERT INTO signal_types (name, description) "
            f"VALUES ('{name}', '{desc}')"
        )


def downgrade() -> None:
    op.execute("DELETE FROM signal_types")
    op.execute("DELETE FROM asset_types")
