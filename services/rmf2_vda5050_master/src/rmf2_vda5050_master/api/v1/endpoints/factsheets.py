from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from vda5050_core.types import Factsheet

from rmf2_vda5050_master import crud
from rmf2_vda5050_master.model_utils import PyModel

from rmf2_vda5050_master.api.deps.db import DbSession
from rmf2_vda5050_master.api.deps.logger import LoggerDeps

router = APIRouter()


@router.get("")
def get_all_factsheets(
    db: DbSession,
    logger: LoggerDeps,
    skip: int = 0,
    limit: int = 100,
) -> list[PyModel[Factsheet]]:
    records = crud.agv_record.get_multi_from_attr(
        db, {"is_onboarded": True}, skip=skip, limit=limit
    )
    return [
        json.loads(r.factsheet_json) for r in records if r.factsheet_json is not None
    ]


@router.get("/{manufacturer}/{serial_number}")
def get_factsheet(
    manufacturer: str,
    serial_number: str,
    db: DbSession,
    logger: LoggerDeps,
) -> PyModel[Factsheet]:
    record = crud.agv_record.get(db, manufacturer, serial_number)
    if record is None or not record.is_onboarded:
        raise HTTPException(status_code=404, detail="AGV not onboarded")
    if record.factsheet_json is None:
        raise HTTPException(status_code=404, detail="No factsheet received yet")
    return json.loads(record.factsheet_json)
