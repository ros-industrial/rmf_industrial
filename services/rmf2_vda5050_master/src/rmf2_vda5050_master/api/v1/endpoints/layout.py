from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from rmf2_vda5050_master import crud
from rmf2_vda5050_master.config import settings

from rmf2_vda5050_master.api.deps.db import DbSession
from rmf2_vda5050_master.api.deps.logger import LoggerDeps
from rmf2_vda5050_master.api.deps.master import MasterDeps

router = APIRouter()


class LifSummary(BaseModel):
    model_config = {"from_attributes": True}

    layout_ids: list[str]
    project_identification: str | None
    creator: str | None
    export_timestamp: str | None
    lif_version: str | None
    loaded_at: datetime


def _get_record(db: DbSession):
    record = crud.lif_record.get_current(db)
    if record is None:
        raise HTTPException(status_code=404, detail="No layout loaded")
    return record


@router.get("")
def get_lif_summary(db: DbSession) -> LifSummary:
    """Return layoutIds and metaInformation for the active LIF."""
    record = _get_record(db)
    layout_ids = json.loads(record.layout_ids_json) if record.layout_ids_json else []
    return LifSummary(
        layout_ids=layout_ids,
        project_identification=record.project_identification,
        creator=record.creator,
        export_timestamp=record.export_timestamp,
        lif_version=record.lif_version,
        loaded_at=record.loaded_at,
    )


@router.get("/download")
def download_lif(db: DbSession) -> Response:
    """Download the entire active LIF as a JSON file."""
    record = _get_record(db)
    filename = (
        f"{record.project_identification}.lif.json"
        if record.project_identification
        else "layout.lif.json"
    )
    return Response(
        content=record.lif_json,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/{layout_id}")
def get_layout(layout_id: str, db: DbSession) -> dict:
    """Return a single layout by layoutId from the active LIF."""
    known_ids = crud.lif_record.get_layout_ids(db)
    if not known_ids:
        raise HTTPException(status_code=404, detail="No layout loaded")
    if layout_id not in known_ids:
        raise HTTPException(status_code=404, detail=f"Layout '{layout_id}' not found")
    record = _get_record(db)
    lif = json.loads(record.lif_json)
    for layout in lif.get("layouts", []):
        if layout.get("layoutId") == layout_id:
            return layout
    raise HTTPException(status_code=404, detail=f"Layout '{layout_id}' not found")


@router.post("")
async def upload_layout(
    file: UploadFile,
    master: MasterDeps,
    db: DbSession,
    logger: LoggerDeps,
) -> dict:
    """Upload and activate a LIF file. Blocked in server mode."""
    if settings().map_mode == "server":
        raise HTTPException(
            status_code=403,
            detail="Layout upload not allowed in server mode; layout is managed by the map server",
        )
    content = await file.read()
    try:
        json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"Invalid JSON: {e}") from e
    with tempfile.NamedTemporaryFile(suffix=".json", mode="wb", delete=False) as f:
        f.write(content)
        tmp_path = Path(f.name)
    try:
        result = master.load_layout_from_config(str(tmp_path))
    finally:
        tmp_path.unlink(missing_ok=True)
    if result.get("errors"):
        logger.warning("Layout loaded with errors: %s", result["errors"])
    else:
        logger.info("Layout loaded via file upload")
    crud.lif_record.set_current(db, content.decode(), datetime.now(timezone.utc))
    return result
