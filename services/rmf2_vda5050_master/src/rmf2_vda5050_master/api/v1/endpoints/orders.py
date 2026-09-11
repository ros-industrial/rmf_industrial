from __future__ import annotations

import json
from datetime import datetime, timezone

import networkx as nx
from fastapi import APIRouter, HTTPException
from vda5050_core.types import Order

from rmf2_vda5050_master import crud
from rmf2_vda5050_master.model_utils import PyModel
from rmf2_vda5050_master.models import (
    OrderAssignmentResult,
    OrderBatch,
    OrderStatus,
    RouteOrderRequest,
)
from rmf2_vda5050_master.order_factory import build_graph, build_order

from rmf2_vda5050_master.api.deps.db import DbSession
from rmf2_vda5050_master.api.deps.logger import LoggerDeps
from rmf2_vda5050_master.api.deps.master import MasterDeps

router = APIRouter()


@router.get("", response_model_exclude_none=True)
def get_all_orders(
    db: DbSession,
    logger: LoggerDeps,
    skip: int = 0,
    limit: int = 100,
    show_order: bool = False,
    show_rejection_errors: bool = True,
) -> list[OrderStatus]:
    records = crud.order_record.get_multi(db, skip=skip, limit=limit)
    ctx = {"show_order": show_order, "show_rejection_errors": show_rejection_errors}
    return [OrderStatus.model_validate(r, context=ctx) for r in records]


@router.get("/{manufacturer}/{serial_number}", response_model_exclude_none=True)
def get_agv_orders(
    manufacturer: str,
    serial_number: str,
    db: DbSession,
    logger: LoggerDeps,
    skip: int = 0,
    limit: int = 100,
    show_order: bool = False,
    show_rejection_errors: bool = True,
) -> list[OrderStatus]:
    records = crud.order_record.get_by_agv(
        db, manufacturer, serial_number, skip=skip, limit=limit
    )
    ctx = {"show_order": show_order, "show_rejection_errors": show_rejection_errors}
    return [OrderStatus.model_validate(r, context=ctx) for r in records]


@router.get("/{manufacturer}/{serial_number}/active")
def get_active_order(
    manufacturer: str,
    serial_number: str,
    db: DbSession,
    logger: LoggerDeps,
) -> PyModel[Order]:
    agv = crud.agv_record.get(db, manufacturer, serial_number)
    if agv is None or not agv.is_onboarded:
        raise HTTPException(status_code=404, detail="AGV not onboarded")
    if agv.active_order_id is None:
        raise HTTPException(status_code=404, detail="No active order")
    record = crud.order_record.get_latest_by_order_id(
        db, manufacturer, serial_number, agv.active_order_id
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Active order record not found")
    return json.loads(record.order_json)


def _do_assign(
    manufacturer: str,
    serial_number: str,
    order: Order,
    master,
    db,
    logger,
) -> OrderAssignmentResult:
    if not master.is_agv_onboarded(manufacturer, serial_number):
        raise HTTPException(
            status_code=404,
            detail=f"AGV not onboarded: {manufacturer}/{serial_number}",
        )
    result = master.assign_order(manufacturer, serial_number, order)
    logger.info(
        "Order assigned to %s/%s: %s", manufacturer, serial_number, result.decision
    )
    crud.order_record.create(
        db,
        manufacturer=manufacturer,
        serial_number=serial_number,
        order_id=order.order_id,
        order_update_id=order.order_update_id,
        order_json=json.dumps(order.json()),
        assigned_at=datetime.now(timezone.utc),
    )
    return OrderAssignmentResult.from_vda5050(result)


@router.post("/{manufacturer}/{serial_number}/assign", response_model_exclude_none=True)
def assign_order(
    manufacturer: str,
    serial_number: str,
    order: PyModel[Order],
    master: MasterDeps,
    db: DbSession,
    logger: LoggerDeps,
) -> OrderAssignmentResult:
    return _do_assign(manufacturer, serial_number, order, master, db, logger)


@router.post("/assign", response_model_exclude_none=True)
def assign_orders(
    orders: list[PyModel[Order]],
    master: MasterDeps,
    db: DbSession,
    logger: LoggerDeps,
) -> list[OrderAssignmentResult]:
    return [
        _do_assign(
            order.header.manufacturer,
            order.header.serial_number,
            order,
            master,
            db,
            logger,
        )
        for order in orders
    ]


@router.post("/{manufacturer}/{serial_number}/assign_shortest_route")
def assign_order_by_shortest_route(
    manufacturer: str,
    serial_number: str,
    body: RouteOrderRequest,
    master: MasterDeps,
    db: DbSession,
    logger: LoggerDeps,
    dry_run: bool = False,
) -> OrderAssignmentResult:
    record = crud.lif_record.get_current(db)
    if record is None:
        raise HTTPException(status_code=404, detail="No layout loaded")

    lif = json.loads(record.lif_json)
    layouts = lif.get("layouts", [])
    if body.layout_id:
        layout = next((l for l in layouts if l.get("layoutId") == body.layout_id), None)
        if layout is None:
            available = [l.get("layoutId") for l in layouts]
            raise HTTPException(status_code=404, detail=f"Layout '{body.layout_id}' not found. Available: {available}")
    elif layouts:
        layout = layouts[0]
    else:
        raise HTTPException(status_code=404, detail="No layouts in LIF")

    graph, node_map = build_graph(layout)
    available = sorted(node_map)
    for node_id in (body.start_node_id, body.end_node_id):
        if node_id not in node_map:
            sample = available[:3]
            hint = f"e.g. {sample}" if len(available) > 3 else str(available)
            raise HTTPException(
                status_code=422,
                detail=f"Node '{node_id}' not found in layout. Available ({len(available)} total): {hint}. Download GET /layout/download for the full list.",
            )

    try:
        path = nx.shortest_path(graph, body.start_node_id, body.end_node_id)
    except nx.NetworkXNoPath:
        raise HTTPException(status_code=422, detail=f"No path from '{body.start_node_id}' to '{body.end_node_id}'")

    order = build_order(
        manufacturer, serial_number, path, graph, node_map, layout.get("layoutId", ""),
        allowed_deviation_xy=body.allowed_deviation_xy,
        allowed_deviation_theta=body.allowed_deviation_theta,
    )
    if dry_run:
        return OrderAssignmentResult(decision="DRY_RUN", errors=[], order=order)
    result = _do_assign(manufacturer, serial_number, order, master, db, logger)
    return OrderAssignmentResult(decision=result.decision, errors=result.errors, order=order)
