from __future__ import annotations

from fastapi import APIRouter, HTTPException

from rmf2_vda5050_master import crud
from rmf2_vda5050_master.master import save_agv
from rmf2_vda5050_master.models import (
    AgvStatus,
    BatchOnboardResult,
    OffboardSpec,
    OnboardSpec,
)

from rmf2_vda5050_master.api.deps.db import DbSession
from rmf2_vda5050_master.api.deps.logger import LoggerDeps
from rmf2_vda5050_master.api.deps.master import MasterDeps

router = APIRouter()


def _make_agv_id(manufacturer: str, serial_number: str) -> str:
    return f"{manufacturer}/{serial_number}"


@router.get("", response_model_exclude_none=True)
def get_onboarded_agvs(
    db: DbSession,
    logger: LoggerDeps,
    skip: int = 0,
    limit: int = 100,
    show_state: bool = False,
    show_connection: bool = False,
    show_factsheet: bool = False,
) -> list[AgvStatus]:
    records = crud.agv_record.get_multi_from_attr(
        db, {"is_onboarded": True}, skip=skip, limit=limit
    )
    ctx = {
        "show_state": show_state,
        "show_connection": show_connection,
        "show_factsheet": show_factsheet,
    }
    return [AgvStatus.model_validate(record, context=ctx) for record in records]


@router.get("/{manufacturer}/{serial_number}", response_model_exclude_none=True)
def get_agv(
    manufacturer: str,
    serial_number: str,
    db: DbSession,
    logger: LoggerDeps,
    show_state: bool = False,
    show_connection: bool = False,
    show_factsheet: bool = False,
) -> AgvStatus:
    record = crud.agv_record.get(db, manufacturer, serial_number)
    if record is None or not record.is_onboarded:
        raise HTTPException(status_code=404, detail="AGV not onboarded")
    ctx = {
        "show_state": show_state,
        "show_connection": show_connection,
        "show_factsheet": show_factsheet,
    }
    return AgvStatus.model_validate(record, context=ctx)


@router.post("/onboard")
def onboard_agvs(
    specs: list[OnboardSpec], master: MasterDeps, db: DbSession, logger: LoggerDeps
) -> BatchOnboardResult:
    for spec in specs:
        save_agv(db, spec.manufacturer, spec.serial_number)
    vda_result = master.onboard_agv_batch([spec.to_vda5050() for spec in specs])
    for spec in vda_result.onboarded:
        logger.info(
            "Onboarded AGV: %s", _make_agv_id(spec.manufacturer, spec.serial_number)
        )
    for spec in vda_result.failed:
        logger.error(
            "Failed to onboard AGV: %s",
            _make_agv_id(spec.manufacturer, spec.serial_number),
        )
        crud.agv_record.update(
            db, spec.manufacturer, spec.serial_number, is_onboarded=False
        )
    return BatchOnboardResult.from_vda5050(vda_result)


@router.post("/{manufacturer}/{serial_number}/onboard")
def onboard_agv(
    manufacturer: str,
    serial_number: str,
    master: MasterDeps,
    db: DbSession,
    logger: LoggerDeps,
) -> OnboardSpec:
    record = crud.agv_record.get(db, manufacturer, serial_number)
    if record is not None and record.is_onboarded:
        raise HTTPException(status_code=409, detail="AGV already onboarded")

    result = master.onboard_agv_batch(
        [
            OnboardSpec(
                manufacturer=manufacturer, serial_number=serial_number
            ).to_vda5050()
        ]
    )
    if result.failed:
        logger.error(
            "Failed to onboard AGV: %s", _make_agv_id(manufacturer, serial_number)
        )
        raise HTTPException(
            status_code=502,
            detail=f"Master failed to onboard {manufacturer}/{serial_number}",
        )

    save_agv(db, manufacturer, serial_number)
    logger.info("Onboarded AGV: %s", _make_agv_id(manufacturer, serial_number))
    return OnboardSpec(manufacturer=manufacturer, serial_number=serial_number)


@router.post("/offboard")
def offboard_agvs(
    specs: list[OffboardSpec], master: MasterDeps, db: DbSession, logger: LoggerDeps
) -> int:
    to_offboard = []
    for spec in specs:
        record = crud.agv_record.get(db, spec.manufacturer, spec.serial_number)
        if record is None or not record.is_onboarded:
            logger.warning(
                "AGV not onboarded, skipping: %s",
                _make_agv_id(spec.manufacturer, spec.serial_number),
            )
        else:
            to_offboard.append(spec)
    if not to_offboard:
        return 0
    count = master.offboard_agv_batch(
        [(spec.manufacturer, spec.serial_number) for spec in to_offboard]
    )
    for spec in to_offboard:
        crud.agv_record.update(
            db,
            spec.manufacturer,
            spec.serial_number,
            is_onboarded=False,
            is_online=False,
        )
        logger.info(
            "Offboarded AGV: %s", _make_agv_id(spec.manufacturer, spec.serial_number)
        )
    return count


@router.post("/{manufacturer}/{serial_number}/offboard")
def offboard_agv(
    manufacturer: str,
    serial_number: str,
    master: MasterDeps,
    db: DbSession,
    logger: LoggerDeps,
) -> int:
    record = crud.agv_record.get(db, manufacturer, serial_number)
    if record is None or not record.is_onboarded:
        raise HTTPException(status_code=404, detail="AGV not onboarded")

    count = master.offboard_agv_batch([(manufacturer, serial_number)])
    crud.agv_record.update(
        db, manufacturer, serial_number, is_onboarded=False, is_online=False
    )
    logger.info("Offboarded AGV: %s", _make_agv_id(manufacturer, serial_number))
    return count
