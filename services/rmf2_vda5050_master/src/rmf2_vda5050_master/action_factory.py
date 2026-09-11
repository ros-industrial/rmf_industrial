from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from vda5050_core.types import Action, ActionParameter, BlockingType, Header, InstantActions  # noqa: F401 — ActionParameter re-exported

from .models import AgvInitConfig


def _header(manufacturer: str, serial_number: str) -> Header:
    h = Header()
    h.header_id = 0
    h.timestamp = datetime.now(timezone.utc).timestamp()
    h.manufacturer = manufacturer
    h.serial_number = serial_number
    h.version = "2.0.0"
    return h


def _action(action_type: str, blocking_type: BlockingType = BlockingType.NONE, params: list[ActionParameter] | None = None) -> Action:
    a = Action()
    a.action_type = action_type
    a.action_id = str(uuid4())
    a.blocking_type = blocking_type
    if params:
        a.action_parameters = params
    return a


def _param(key: str, value: str) -> ActionParameter:
    p = ActionParameter()
    p.key = key
    p.value = value
    return p


def _build(manufacturer: str, serial_number: str, *actions: Action) -> InstantActions:
    ia = InstantActions()
    ia.header = _header(manufacturer, serial_number)
    ia.actions = list(actions)
    return ia


def make_state_request(manufacturer: str, serial_number: str) -> InstantActions:
    return _build(manufacturer, serial_number, _action("stateRequest"))


def make_factsheet_request(manufacturer: str, serial_number: str) -> InstantActions:
    return _build(manufacturer, serial_number, _action("factsheetRequest"))


def make_init_position(
    manufacturer: str, serial_number: str, init_config: AgvInitConfig | None, state
) -> InstantActions:
    pos = state.agv_position

    def _pick_pos(cfg_val, attr: str, default):
        if cfg_val is not None:
            return cfg_val
        return getattr(pos, attr) if pos is not None else default

    def _pick_state(cfg_val, attr: str, default):
        if cfg_val is not None:
            return cfg_val
        return getattr(state, attr) if state is not None else default

    ic = init_config
    params = [
        _param("x", str(_pick_pos(ic.x if ic else None, "x", 0.0))),
        _param("y", str(_pick_pos(ic.y if ic else None, "y", 0.0))),
        _param("theta", str(_pick_pos(ic.theta if ic else None, "theta", 0.0))),
        _param("mapId", str(_pick_pos(ic.map_id if ic else None, "map_id", ""))),
        _param("lastNodeId", str(_pick_state(ic.last_node_id if ic else None, "last_node_id", ""))),
        _param("lastNodeSequenceId", "0"),
    ]
    return _build(manufacturer, serial_number, _action("initPosition", params=params))


def make_custom(
    manufacturer: str,
    serial_number: str,
    action_type: str,
    blocking_type: str = "NONE",
    params: list[ActionParameter] | None = None,
) -> InstantActions:
    return _build(manufacturer, serial_number, _action(action_type, getattr(BlockingType, blocking_type), params))
