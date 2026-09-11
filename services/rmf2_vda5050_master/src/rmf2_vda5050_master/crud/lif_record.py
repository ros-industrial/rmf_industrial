from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from rmf2_vda5050_master.db_models import LifRecord

_SINGLETON_ID = 1


def get_current(db: Session) -> LifRecord | None:
    return db.query(LifRecord).filter(LifRecord.id == _SINGLETON_ID).first()


def get_layout_ids(db: Session) -> list[str]:
    record = get_current(db)
    if record is None or record.layout_ids_json is None:
        return []
    return json.loads(record.layout_ids_json)


def set_current(db: Session, lif_json: str, loaded_at: datetime) -> LifRecord:
    lif = json.loads(lif_json)
    layout_ids = [
        layout["layoutId"] for layout in lif.get("layouts", []) if "layoutId" in layout
    ]
    meta = lif.get("metaInformation", {})
    record = get_current(db)
    if record is None:
        record = LifRecord(
            id=_SINGLETON_ID,
            lif_json=lif_json,
            loaded_at=loaded_at,
            layout_ids_json=json.dumps(layout_ids),
            project_identification=meta.get("projectIdentification"),
            creator=meta.get("creator"),
            export_timestamp=meta.get("exportTimestamp"),
            lif_version=meta.get("lifVersion"),
        )
        db.add(record)
    else:
        record.lif_json = lif_json
        record.loaded_at = loaded_at
        record.layout_ids_json = json.dumps(layout_ids)
        record.project_identification = meta.get("projectIdentification")
        record.creator = meta.get("creator")
        record.export_timestamp = meta.get("exportTimestamp")
        record.lif_version = meta.get("lifVersion")
    db.commit()
    db.refresh(record)
    return record
