from datetime import datetime

from pydantic import BaseModel


class AssetTypeResponse(BaseModel):
    id: int
    name: str
    isa95_level: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
