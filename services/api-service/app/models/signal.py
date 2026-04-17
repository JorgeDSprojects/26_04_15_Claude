from datetime import datetime

from sqlalchemy import (
    Boolean,
    Double,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

criticality_enum = Enum(
    "standard", "buffered", "critical", name="criticality_level", create_type=False
)
datatype_enum = Enum(
    "float", "int", "bool", "string", "enum", name="signal_datatype", create_type=False
)


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint("asset_id", "name", name="uq_signals_asset_name"),
        Index("idx_signals_asset", "asset_id"),
        Index("idx_signals_topic", "topic"),
        Index(
            "idx_signals_enabled",
            "enabled",
            postgresql_where="enabled = true",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    signal_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("signal_types.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str | None] = mapped_column(Text)
    datatype: Mapped[str] = mapped_column(datatype_enum, nullable=False)
    criticality: Mapped[str] = mapped_column(
        criticality_enum, nullable=False, default="standard"
    )
    topic: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    protocol: Mapped[str | None] = mapped_column(Text)
    connection_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    polling_interval_ms: Mapped[int | None] = mapped_column(Integer)

    min_value: Mapped[float | None] = mapped_column(Double)
    max_value: Mapped[float | None] = mapped_column(Double)
    enum_values: Mapped[dict | None] = mapped_column(JSONB)

    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    asset = relationship("Asset", back_populates="signals", lazy="selectin")
    signal_type = relationship("SignalType", lazy="selectin")
