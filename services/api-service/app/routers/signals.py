from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.asset import Asset
from app.models.signal import Signal
from app.models.signal_type import SignalType
from app.schemas.signal import SignalCreate, SignalResponse, SignalUpdate
from app.services.topic_builder import compute_topic

router = APIRouter(prefix="/api/v1/signals", tags=["signals"])


@router.get("", response_model=list[SignalResponse])
async def list_signals(
    asset_id: int | None = None,
    criticality: str | None = None,
    enabled: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Signal).order_by(Signal.id)
    if asset_id is not None:
        q = q.where(Signal.asset_id == asset_id)
    if criticality is not None:
        q = q.where(Signal.criticality == criticality)
    if enabled is not None:
        q = q.where(Signal.enabled == enabled)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=SignalResponse, status_code=201)
async def create_signal(body: SignalCreate, db: AsyncSession = Depends(get_db)):
    asset_result = await db.execute(select(Asset).where(Asset.id == body.asset_id))
    asset = asset_result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    st_result = await db.execute(
        select(SignalType).where(SignalType.id == body.signal_type_id)
    )
    signal_type = st_result.scalar_one_or_none()
    if not signal_type:
        raise HTTPException(status_code=404, detail="Signal type not found")

    topic = compute_topic(asset.path, signal_type.name, body.name)

    signal = Signal(
        asset_id=body.asset_id,
        signal_type_id=body.signal_type_id,
        name=body.name,
        display_name=body.display_name,
        unit=body.unit,
        datatype=body.datatype,
        criticality=body.criticality,
        topic=topic,
        enabled=body.enabled,
        protocol=body.protocol,
        connection_config=body.connection_config,
        polling_interval_ms=body.polling_interval_ms,
        min_value=body.min_value,
        max_value=body.max_value,
        enum_values=body.enum_values,
        metadata_=body.metadata_,
    )
    db.add(signal)
    await db.commit()
    await db.refresh(signal)
    return signal


@router.get("/{signal_id}", response_model=SignalResponse)
async def get_signal(signal_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Signal).where(Signal.id == signal_id))
    signal = result.scalar_one_or_none()
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    return signal


@router.patch("/{signal_id}", response_model=SignalResponse)
async def update_signal(
    signal_id: int, body: SignalUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Signal).where(Signal.id == signal_id))
    signal = result.scalar_one_or_none()
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(signal, field, value)

    await db.commit()
    await db.refresh(signal)
    return signal


@router.delete("/{signal_id}", status_code=204)
async def delete_signal(signal_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Signal).where(Signal.id == signal_id))
    signal = result.scalar_one_or_none()
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    await db.delete(signal)
    await db.commit()
