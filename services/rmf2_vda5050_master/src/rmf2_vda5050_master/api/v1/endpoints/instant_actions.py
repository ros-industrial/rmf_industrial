from __future__ import annotations

from fastapi import APIRouter, HTTPException
from vda5050_core.types import InstantActions

from rmf2_vda5050_master.action_factory import (
    make_custom,
    make_factsheet_request,
    make_init_position,
    make_state_request,
)
from rmf2_vda5050_master.model_utils import PyModel
from rmf2_vda5050_master.models import AgvInitConfig, CustomInstantActionRequest, InstantActionsResult

from rmf2_vda5050_master.api.deps.logger import LoggerDeps
from rmf2_vda5050_master.api.deps.master import MasterDeps

router = APIRouter()


def _do_assign(
    manufacturer: str,
    serial_number: str,
    actions: InstantActions,
    master,
    logger,
) -> InstantActionsResult:
    if not master.is_agv_onboarded(manufacturer, serial_number):
        raise HTTPException(
            status_code=404,
            detail=f"AGV not onboarded: {manufacturer}/{serial_number}",
        )
    result = master.assign_instant_actions(manufacturer, serial_number, actions)
    logger.info(
        "InstantActions sent to %s/%s — decision: %s",
        manufacturer,
        serial_number,
        result.decision,
    )
    return InstantActionsResult.from_vda5050(result)


@router.post("/{manufacturer}/{serial_number}/assign", response_model_exclude_none=True)
def assign_instant_actions(
    manufacturer: str,
    serial_number: str,
    actions: PyModel[InstantActions],
    master: MasterDeps,
    logger: LoggerDeps,
) -> InstantActionsResult:
    return _do_assign(manufacturer, serial_number, actions, master, logger)


@router.post("/assign", response_model_exclude_none=True)
def assign_instant_actions_batch(
    actions_list: list[PyModel[InstantActions]],
    master: MasterDeps,
    logger: LoggerDeps,
) -> list[InstantActionsResult]:
    return [
        _do_assign(
            a.header.manufacturer,
            a.header.serial_number,
            a,
            master,
            logger,
        )
        for a in actions_list
    ]


def _dry_run(actions) -> InstantActionsResult:
    return InstantActionsResult(decision="DRY_RUN", errors=[], instant_actions=actions)


@router.post("/{manufacturer}/{serial_number}/state_request")
def state_request(
    manufacturer: str,
    serial_number: str,
    master: MasterDeps,
    logger: LoggerDeps,
    dry_run: bool = False,
) -> InstantActionsResult:
    actions = make_state_request(manufacturer, serial_number)
    if dry_run:
        return _dry_run(actions)
    result = _do_assign(manufacturer, serial_number, actions, master, logger)
    return InstantActionsResult(decision=result.decision, errors=result.errors, instant_actions=actions)


@router.post("/{manufacturer}/{serial_number}/factsheet_request")
def factsheet_request(
    manufacturer: str,
    serial_number: str,
    master: MasterDeps,
    logger: LoggerDeps,
    dry_run: bool = False,
) -> InstantActionsResult:
    actions = make_factsheet_request(manufacturer, serial_number)
    if dry_run:
        return _dry_run(actions)
    result = _do_assign(manufacturer, serial_number, actions, master, logger)
    return InstantActionsResult(decision=result.decision, errors=result.errors, instant_actions=actions)


@router.post("/{manufacturer}/{serial_number}/custom")
def custom_instant_action(
    manufacturer: str,
    serial_number: str,
    body: CustomInstantActionRequest,
    master: MasterDeps,
    logger: LoggerDeps,
    dry_run: bool = False,
) -> InstantActionsResult:
    actions = make_custom(manufacturer, serial_number, body.action_type, body.blocking_type, body.params)
    if dry_run:
        return _dry_run(actions)
    result = _do_assign(manufacturer, serial_number, actions, master, logger)
    return InstantActionsResult(decision=result.decision, errors=result.errors, instant_actions=actions)


@router.post("/{manufacturer}/{serial_number}/init_position")
def init_position(
    manufacturer: str,
    serial_number: str,
    master: MasterDeps,
    logger: LoggerDeps,
    init_config: AgvInitConfig | None = None,
    dry_run: bool = False,
) -> InstantActionsResult:
    agv = master.get_agv(manufacturer, serial_number)
    if agv is None:
        raise HTTPException(status_code=404, detail=f"AGV not onboarded: {manufacturer}/{serial_number}")
    state = agv.get_last_state()
    if state is None:
        raise HTTPException(status_code=409, detail=f"No state received yet from {manufacturer}/{serial_number}")
    actions = make_init_position(manufacturer, serial_number, init_config, state)
    if dry_run:
        return _dry_run(actions)
    result = _do_assign(manufacturer, serial_number, actions, master, logger)
    return InstantActionsResult(decision=result.decision, errors=result.errors, instant_actions=actions)
