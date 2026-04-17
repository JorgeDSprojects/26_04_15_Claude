from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.signal_type import SignalType
from app.schemas.signal_type import SignalTypeResponse

router = APIRouter(prefix="/api/v1/signal-types", tags=["signal-types"])


@router.get("", response_model=list[SignalTypeResponse])
async def list_signal_types(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SignalType).order_by(SignalType.id))
    return result.scalars().all()


@router.get("/{signal_type_id}", response_model=SignalTypeResponse)
async def get_signal_type(signal_type_id: int, db: AsyncSession = Depends(get_db)):
    from fastapi import HTTPException

    result = await db.execute(
        select(SignalType).where(SignalType.id == signal_type_id)
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Signal type not found")
    return obj
