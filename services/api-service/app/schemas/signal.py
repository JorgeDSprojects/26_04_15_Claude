from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

CriticalityLevel = Literal["standard", "buffered", "critical"]
SignalDatatype = Literal["float", "int", "bool", "string", "enum"]


class SignalCreate(BaseModel):
    asset_id: int
    signal_type_id: int
    name: str
    display_name: str
    unit: str | None = None
    datatype: SignalDatatype
    criticality: CriticalityLevel = "standard"
    enabled: bool = True
    protocol: str | None = None
    connection_config: dict[str, Any] = {}
    polling_interval_ms: int | None = None
    min_value: float | None = None
    max_value: float | None = None
    enum_values: dict[str, Any] | None = None
    metadata_: dict[str, Any] = {}

    model_config = {"populate_by_name": True}


class SignalUpdate(BaseModel):
    display_name: str | None = None
    unit: str | None = None
    criticality: CriticalityLevel | None = None
    enabled: bool | None = None
    protocol: str | None = None
    connection_config: dict[str, Any] | None = None
    polling_interval_ms: int | None = None
    min_value: float | None = None
    max_value: float | None = None
    enum_values: dict[str, Any] | None = None
    metadata_: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


class SignalResponse(BaseModel):
    id: int
    asset_id: int
    signal_type_id: int
    name: str
    display_name: str
    unit: str | None
    datatype: str
    criticality: str
    topic: str
    enabled: bool
    protocol: str | None
    connection_config: dict[str, Any]
    polling_interval_ms: int | None
    min_value: float | None
    max_value: float | None
    enum_values: dict[str, Any] | None
    metadata_: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}
