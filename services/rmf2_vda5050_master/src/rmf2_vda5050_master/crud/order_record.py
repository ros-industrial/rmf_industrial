from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from rmf2_vda5050_master.db_models import OrderRecord

from .base import CRUDBase

_OrderRecordCreate = dict[str, str | int | datetime]


def _make_internal_order_id(
    manufacturer: str, serial_number: str, order_id: str
) -> str:
    return f"{manufacturer}/{serial_number}/{order_id}"


class CRUDOrderRecord(CRUDBase[OrderRecord, _OrderRecordCreate, _OrderRecordCreate]):
    def create(  # type: ignore[override]
        self,
        db: Session,
        manufacturer: str,
        serial_number: str,
        order_id: str,
        order_update_id: int,
        order_json: str,
        assigned_at: datetime,
    ) -> OrderRecord:
        return super().create(
            db,
            obj_in={
                "internal_order_id": _make_internal_order_id(
                    manufacturer, serial_number, order_id
                ),
                "manufacturer": manufacturer,
                "serial_number": serial_number,
                "order_id": order_id,
                "order_update_id": order_update_id,
                "order_json": order_json,
                "assigned_at": assigned_at,
            },
        )

    def get_by_order_id(
        self,
        db: Session,
        manufacturer: str,
        serial_number: str,
        order_id: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[OrderRecord]:
        internal_id = _make_internal_order_id(manufacturer, serial_number, order_id)
        return (
            db.query(OrderRecord)
            .filter(OrderRecord.internal_order_id == internal_id)
            .order_by(OrderRecord.order_update_id.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_latest_by_order_id(
        self,
        db: Session,
        manufacturer: str,
        serial_number: str,
        order_id: str,
    ) -> OrderRecord | None:
        internal_id = _make_internal_order_id(manufacturer, serial_number, order_id)
        return (
            db.query(OrderRecord)
            .filter(OrderRecord.internal_order_id == internal_id)
            .order_by(
                OrderRecord.assigned_at.desc(), OrderRecord.order_update_id.desc()
            )
            .first()
        )

    def get_by_agv(
        self,
        db: Session,
        manufacturer: str,
        serial_number: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[OrderRecord]:
        return (
            db.query(OrderRecord)
            .filter(
                OrderRecord.manufacturer == manufacturer,
                OrderRecord.serial_number == serial_number,
            )
            .order_by(OrderRecord.assigned_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )


order_record = CRUDOrderRecord(OrderRecord)
