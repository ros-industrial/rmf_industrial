from importlib.metadata import version as pkg_version

from fastapi import APIRouter

from rmf2_vda5050_master.models import InfoResponse

router = APIRouter()


@router.get("")
async def info() -> InfoResponse:
    return InfoResponse(
        service_version=pkg_version("rmf2-vda5050-master"),
        api_version="v1",
        vda5050_versions=["2.0.0"],
    )
