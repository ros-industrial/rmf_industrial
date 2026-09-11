from __future__ import annotations

from fastapi import APIRouter, HTTPException
from vda5050_core.types import Visualization

from rmf2_vda5050_master import crud
from rmf2_vda5050_master.model_utils import PyModel

from rmf2_vda5050_master.api.deps.db import DbSession
from rmf2_vda5050_master.api.deps.master import MasterDeps

router = APIRouter()


def _get_viz(manufacturer: str, serial_number: str, master):
    if not master.is_agv_onboarded(manufacturer, serial_number):
        raise HTTPException(status_code=404, detail="AGV not onboarded")
    viz = master.get_agv(manufacturer, serial_number).get_last_visualization()
    if viz is None:
        raise HTTPException(status_code=404, detail="No visualization received yet")
    return viz


@router.get("")
def get_all_visualizations(
    master: MasterDeps,
    db: DbSession,
    skip: int = 0,
    limit: int = 100,
) -> dict[str, PyModel[Visualization]]:
    """Return the latest Visualization for all onboarded AGVs that have one."""
    records = crud.agv_record.get_multi_from_attr(
        db, {"is_onboarded": True}, skip=skip, limit=limit
    )
    result = {}
    for record in records:
        viz = master.get_agv(
            record.manufacturer, record.serial_number
        ).get_last_visualization()
        if viz is not None:
            result[record.agv_id] = viz
    return result


@router.get("/{manufacturer}/{serial_number}")
def get_visualization(
    manufacturer: str,
    serial_number: str,
    master: MasterDeps,
) -> PyModel[Visualization]:
    """Return the latest Visualization message for an AGV."""
    return _get_viz(manufacturer, serial_number, master)
