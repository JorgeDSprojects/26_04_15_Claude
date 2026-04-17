from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AssetCreate(BaseModel):
    parent_id: int | None = None
    asset_type_id: int
    code: str
    display_name: str
    path: str
    metadata_: dict[str, Any] = {}

    model_config = {"populate_by_name": True}


class AssetUpdate(BaseModel):
    display_name: str | None = None
    metadata_: dict[str, Any] | None = None


class AssetResponse(BaseModel):
    id: int
    parent_id: int | None
    asset_type_id: int
    code: str
    display_name: str
    path: str
    metadata_: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}
