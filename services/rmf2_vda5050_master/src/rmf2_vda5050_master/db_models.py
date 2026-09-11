from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class LifRecord(Base):
    """Stores the currently active LIF layout. At most one row (id=1)."""

    __tablename__ = "lif_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    lif_json: Mapped[str] = mapped_column(Text)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # JSON array of all layoutId strings from lif_json, kept in sync for fast lookup
    layout_ids_json: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    # metaInformation fields stored individually for easy lookup
    project_identification: Mapped[str | None] = mapped_column(
        String, nullable=True, default=None
    )
    creator: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    export_timestamp: Mapped[str | None] = mapped_column(
        String, nullable=True, default=None
    )
    lif_version: Mapped[str | None] = mapped_column(String, nullable=True, default=None)


class OrderRecord(Base):
    __tablename__ = "order_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    internal_order_id: Mapped[str] = mapped_column(String, index=True)
    manufacturer: Mapped[str] = mapped_column(String, index=True)
    serial_number: Mapped[str] = mapped_column(String, index=True)
    order_id: Mapped[str] = mapped_column(String, index=True)
    order_update_id: Mapped[int] = mapped_column(Integer)
    order_json: Mapped[str] = mapped_column(Text)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    rejection_errors_json: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )


class AgvRecord(Base):
    __tablename__ = "agv_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    agv_id: Mapped[str] = mapped_column(String, index=True, unique=True)
    manufacturer: Mapped[str] = mapped_column(String)
    serial_number: Mapped[str] = mapped_column(String)
    is_onboarded: Mapped[bool] = mapped_column(default=False)
    is_online: Mapped[bool] = mapped_column(default=False)
    connection_json: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    connection_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    state_json: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    state_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    factsheet_json: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    factsheet_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    active_order_id: Mapped[str | None] = mapped_column(
        String, nullable=True, default=None
    )
