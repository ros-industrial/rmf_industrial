from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from vda5050_core.types import State

from rmf2_vda5050_master import crud
from rmf2_vda5050_master.model_utils import PyModel

from rmf2_vda5050_master.api.deps.db import DbSession
from rmf2_vda5050_master.api.deps.logger import LoggerDeps

router = APIRouter()


@router.get("")
def get_all_states(
    db: DbSession, logger: LoggerDeps, skip: int = 0, limit: int = 100
) -> list[PyModel[State]]:
    records = crud.agv_record.get_multi_from_attr(
        db, {"is_onboarded": True}, skip=skip, limit=limit
    )
    return [json.loads(r.state_json) for r in records if r.state_json is not None]


@router.get("/{manufacturer}/{serial_number}")
def get_state(
    db: DbSession, logger: LoggerDeps, manufacturer: str, serial_number: str
) -> PyModel[State]:
    record = crud.agv_record.get(db, manufacturer, serial_number)
    if record is None or not record.is_onboarded:
        raise HTTPException(status_code=404, detail="AGV not onboarded")
    if record.state_json is None:
        raise HTTPException(status_code=404, detail="No state received yet")
    return json.loads(record.state_json)
