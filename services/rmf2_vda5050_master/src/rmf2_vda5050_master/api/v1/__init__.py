from fastapi import APIRouter

from .endpoints import (
    agvs,
    connections,
    factsheets,
    instant_actions,
    layout,
    orders,
    states,
    visualization,
)

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(layout.router, prefix="/layout", tags=["layout"])
v1_router.include_router(agvs.router, prefix="/agvs", tags=["agvs"])
v1_router.include_router(connections.router, prefix="/connections", tags=["connections"])
v1_router.include_router(factsheets.router, prefix="/factsheets", tags=["factsheets"])
v1_router.include_router(states.router, prefix="/states", tags=["states"])
v1_router.include_router(orders.router, prefix="/orders", tags=["orders"])
v1_router.include_router(instant_actions.router, prefix="/instant_actions", tags=["instant_actions"])
v1_router.include_router(visualization.router, prefix="/visualizations", tags=["visualizations"])
