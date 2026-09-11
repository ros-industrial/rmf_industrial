from fastapi import APIRouter

from .v1 import v1_router
from . import health, info

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(info.router, prefix="/info", tags=["info"])
api_router.include_router(v1_router)
