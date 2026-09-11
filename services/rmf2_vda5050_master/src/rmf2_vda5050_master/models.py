"""TypedDict models and PyModel schema registrations for vda5050_core types."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationInfo,
    field_validator,
    model_validator,
)
from vda5050_core.master import (
    OnboardSpec as _VdaOnboardSpec,
)
from vda5050_core.types import (
    AGVPosition,
    ActionParameter,
    Connection,
    ConnectionState,
    Error,
    Factsheet,
    InstantActions,
    Order,
    State,
    Visualization,
)

from .model_utils import FromVda5050, PyModel

_SCHEMAS = Path(__file__).parent / "schemas"

PyModel.register(State, _SCHEMAS / "state.schema.json")
PyModel.register(AGVPosition, _SCHEMAS / "state.schema.json", property_path="properties.agvPosition")
PyModel.register(InstantActions, _SCHEMAS / "instantActions.schema.json")
PyModel.register(ActionParameter, _SCHEMAS / "instantActions.schema.json", property_path="properties.actions.items.properties.actionParameters.items")
PyModel.register(Connection, _SCHEMAS / "connection.schema.json")
PyModel.register(
    Error, _SCHEMAS / "state.schema.json", property_path="properties.errors.items"
)
PyModel.register(Order, _SCHEMAS / "order.schema.json")
PyModel.register(Factsheet, _SCHEMAS / "factsheet.schema.json")
PyModel.register(Visualization, _SCHEMAS / "visualization.schema.json")

_connection_adapter = TypeAdapter(PyModel[Connection])


class AgvInitConfig(BaseModel):
    x: float | None = None
    y: float | None = None
    theta: float | None = None
    last_node_id: str | None = None
    map_id: str | None = None


class AgvConfig(BaseModel):
    manufacturer: str
    serial_number: str
    init_config: AgvInitConfig | None = None


class AgvStatus(AgvConfig):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    is_online: bool
    active_order_id: str | None = None
    state: PyModel[State] | None = Field(None, validation_alias="state_json")
    connection: PyModel[Connection] | None = Field(
        None, validation_alias="connection_json"
    )
    factsheet: PyModel[Factsheet] | None = Field(
        None, validation_alias="factsheet_json"
    )

    @field_validator("state", "connection", "factsheet", mode="before")
    @classmethod
    def _parse_json(cls, value: str | None, info: ValidationInfo) -> dict | None:
        if not (info.context or {}).get(f"show_{info.field_name}", False):
            return None
        return json.loads(value) if value is not None else None


class OffboardSpec(BaseModel):
    manufacturer: str = Field(description="AGV manufacturer identifier")
    serial_number: str = Field(description="AGV serial number")


class OnboardSpec(FromVda5050):
    manufacturer: str
    serial_number: str
    max_queue_size: int = 10
    drop_oldest: bool = True

    def to_vda5050(self) -> _VdaOnboardSpec:
        return _VdaOnboardSpec(**self.model_dump())


class BatchOnboardResult(FromVda5050):
    onboarded: list[OnboardSpec]
    failed: list[OnboardSpec]
    skipped_already_onboarded: list[OnboardSpec]


class OrderStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    manufacturer: str
    serial_number: str
    order_id: str
    order_update_id: int
    assigned_at: datetime
    completed_at: datetime | None = None
    rejected_at: datetime | None = None
    rejection_errors: list[PyModel[Error]] | None = Field(
        None, validation_alias="rejection_errors_json"
    )
    order: PyModel[Order] | None = Field(None, validation_alias="order_json")

    @field_validator("rejection_errors", "order", mode="before")
    @classmethod
    def _parse_json_fields(cls, value: str | None, info: ValidationInfo):
        if not (info.context or {}).get(f"show_{info.field_name}", False):
            return None
        return json.loads(value) if value is not None else None


class OrderBatch(BaseModel):
    orders: list[PyModel[Order]]


class OrderAssignmentResult(FromVda5050):
    decision: str
    errors: list[PyModel[Error]]
    order: PyModel[Order] | None = None


class InstantActionsResult(FromVda5050):
    decision: str
    errors: list[PyModel[Error]]
    instant_actions: PyModel[InstantActions] | None = None


class CustomInstantActionRequest(BaseModel):
    action_type: str
    blocking_type: str = "NONE"
    params: list[PyModel[ActionParameter]] | None = None


class RouteOrderRequest(BaseModel):
    start_node_id: str
    end_node_id: str
    layout_id: str | None = None
    allowed_deviation_xy: float | None = None
    allowed_deviation_theta: float | None = None



class HealthResponse(BaseModel):
    status: str


class InfoResponse(BaseModel):
    service_version: str
    api_version: str
    vda5050_versions: list[str]


class DeviceConnection(BaseModel):
    timestamp: str
    deviceId: str
    connectionState: Literal["ONLINE", "OFFLINE"]

    @model_validator(mode="wrap")
    @classmethod
    def from_vda5050_connection(cls, data, handler):
        if isinstance(data, cls):
            return data
        conn: Connection = _connection_adapter.validate_python(data)
        return cls.model_construct(
            timestamp=datetime.fromtimestamp(
                conn.header.timestamp, tz=timezone.utc
            ).isoformat(),
            deviceId=f"{conn.header.manufacturer}/{conn.header.serial_number}",
            connectionState="ONLINE"
            if conn.connection_state == ConnectionState.ONLINE
            else "OFFLINE",
        )
