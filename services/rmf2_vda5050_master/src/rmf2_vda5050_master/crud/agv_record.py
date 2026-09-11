from __future__ import annotations

from sqlalchemy.orm import Session

from rmf2_vda5050_master.db_models import AgvRecord

from .base import CRUDBase

_AGVRecordCreate = dict[str, str | bool | None]


def _make_agv_id(manufacturer: str, serial_number: str) -> str:
    return f"{manufacturer}/{serial_number}"


class CRUDAgvRecord(CRUDBase[AgvRecord, _AGVRecordCreate, _AGVRecordCreate]):
    def get(
        self, db: Session, manufacturer: str, serial_number: str
    ) -> AgvRecord | None:  # type: ignore[override]
        return self.get_from_attr(
            db, "agv_id", _make_agv_id(manufacturer, serial_number)
        )

    def create(
        self, db: Session, manufacturer: str, serial_number: str, **kwargs
    ) -> AgvRecord:  # type: ignore[override]
        agv_id = _make_agv_id(manufacturer, serial_number)
        return super().create(
            db,
            obj_in={
                "agv_id": agv_id,
                "manufacturer": manufacturer,
                "serial_number": serial_number,
                **kwargs,
            },
        )

    def update(
        self, db: Session, manufacturer: str, serial_number: str, **kwargs
    ) -> AgvRecord:  # type: ignore[override]
        return super().update(
            db, db_obj=self.get(db, manufacturer, serial_number), obj_in=kwargs
        )

    def reset_all_onboarded(self, db: Session) -> list[str]:
        records = db.query(AgvRecord).filter(AgvRecord.is_onboarded == True).all()
        agv_ids = [r.agv_id for r in records]
        for r in records:
            db.delete(r)
        db.commit()
        return agv_ids


agv_record = CRUDAgvRecord(AgvRecord)
