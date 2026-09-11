from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from rmf2_vda5050_master import crud
from rmf2_vda5050_master.models import DeviceConnection

from rmf2_vda5050_master.api.deps.db import DbSession
from rmf2_vda5050_master.api.deps.logger import LoggerDeps

router = APIRouter()


@router.get("")
def get_all_connections(
    db: DbSession, logger: LoggerDeps, skip: int = 0, limit: int = 100
) -> list[DeviceConnection]:
    records = crud.agv_record.get_multi_from_attr(
        db, {"is_onboarded": True}, skip=skip, limit=limit
    )
    return [
        DeviceConnection.model_validate(json.loads(r.connection_json))
        for r in records
        if r.connection_json is not None
    ]


@router.get("/{manufacturer}/{serial_number}")
def get_connection(
    db: DbSession, logger: LoggerDeps, manufacturer: str, serial_number: str
) -> DeviceConnection:
    record = crud.agv_record.get(db, manufacturer, serial_number)
    if record is None or not record.is_onboarded:
        raise HTTPException(status_code=404, detail="AGV not onboarded")
    if record.connection_json is None:
        raise HTTPException(status_code=404, detail="No connection state received yet")
    return DeviceConnection.model_validate(json.loads(record.connection_json))
