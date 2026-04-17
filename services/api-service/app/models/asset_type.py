from datetime import datetime

from sqlalchemy import CheckConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AssetType(Base):
    __tablename__ = "asset_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    isa95_level: Mapped[str] = mapped_column(
        Text,
        CheckConstraint(
            "isa95_level IN ('enterprise','site','area','line','cell')",
            name="ck_asset_types_isa95_level",
        ),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
