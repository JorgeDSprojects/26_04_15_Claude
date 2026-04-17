from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.asset_type import AssetType
from app.schemas.asset_type import AssetTypeResponse

router = APIRouter(prefix="/api/v1/asset-types", tags=["asset-types"])


@router.get("", response_model=list[AssetTypeResponse])
async def list_asset_types(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AssetType).order_by(AssetType.id))
    return result.scalars().all()


@router.get("/{asset_type_id}", response_model=AssetTypeResponse)
async def get_asset_type(asset_type_id: int, db: AsyncSession = Depends(get_db)):
    from fastapi import HTTPException

    result = await db.execute(
        select(AssetType).where(AssetType.id == asset_type_id)
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Asset type not found")
    return obj
