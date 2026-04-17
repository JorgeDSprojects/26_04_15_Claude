from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SignalType(Base):
    __tablename__ = "signal_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
