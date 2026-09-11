from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from vda5050_core.master import VDA5050Master


def get_master(request: Request) -> VDA5050Master:
    """Read the VDA5050Master from app.state.

    The master is created and connected in the FastAPI lifespan (app.py),
    with all configured AGVs onboarded before the app begins serving requests.
    On shutdown, AGVs are offboarded and the master is disconnected.
    """
    master: VDA5050Master | None = getattr(request.app.state, "master", None)
    if master is None:
        raise HTTPException(status_code=503, detail="Master not ready")
    return master


MasterDeps = Annotated[VDA5050Master, Depends(get_master)]
