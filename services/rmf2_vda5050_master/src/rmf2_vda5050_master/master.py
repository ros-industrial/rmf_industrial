from __future__ import annotations

import json
import os
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker
from vda5050_core.master import OnboardSpec, VDA5050Master
from vda5050_core.transport import create_default_client_shared as create_mqtt_client
from vda5050_core.types import (
    Connection,
    ConnectionState,
    Factsheet,
    InstantActions,
    Order,
    State,
    Visualization,
)

from . import crud
from .action_factory import make_factsheet_request, make_init_position, make_state_request
from .config import Settings
from .logger import get_logger
from .models import (
    InstantActionsResult,
    OrderAssignmentResult,
    OrderBatch,
)
from .models import AgvConfig, AgvInitConfig
from .transport import DeliveryMode, Heartbeat, PublisherBase, ServerTransportBase

LOGGER = get_logger(__name__)


def _parse_agv_id(agv_id: str) -> tuple[str, str]:
    parts = agv_id.split("/", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (agv_id, "")


_FRESH_AGV_STATE = {
    "is_onboarded": True,
    "is_online": False,
    "connection_json": None,
    "connection_updated_at": None,
    "state_json": None,
    "state_updated_at": None,
    "factsheet_json": None,
    "factsheet_updated_at": None,
    "active_order_id": None,
}


def save_agv(db: Session, manufacturer: str, serial_number: str) -> None:
    if crud.agv_record.get(db, manufacturer, serial_number) is None:
        crud.agv_record.create(db, manufacturer, serial_number, **_FRESH_AGV_STATE)
    else:
        crud.agv_record.update(db, manufacturer, serial_number, **_FRESH_AGV_STATE)



class _MasterObserver:
    def __init__(
        self,
        master: VDA5050Master,
        session_factory: sessionmaker[Session],
        transport: ServerTransportBase | None = None,
        topic_prefix: str | None = None,
        heartbeat: Heartbeat | None = None,
        agv_configs: list[AgvConfig] | None = None,
    ) -> None:
        self._master = master
        self._session_factory = session_factory
        self._transport = transport
        self._topic_prefix = topic_prefix
        self._pubs: dict[str, PublisherBase] = {}
        self._heartbeat = heartbeat
        self._heartbeat_registered: set[str] = set()
        self._agv_configs: dict[str, AgvConfig] = {
            f"{c.manufacturer}/{c.serial_number}": c for c in (agv_configs or [])
        }

    def _full_topic(self, topic: str) -> str:
        return f"{self._topic_prefix}/{topic}" if self._topic_prefix else topic

    def _publish(self, message_type: type, topic: str, message, **pub_kwargs) -> None:
        if self._transport is not None and topic not in self._pubs:
            self._pubs[topic] = self._transport.create_publisher(
                message_type, self._full_topic(topic), **pub_kwargs
            )
        pub = self._pubs.get(topic)
        if pub:
            pub.publish(message)

    def _update_if_registered(
        self, manufacturer: str, serial_number: str, **kwargs
    ) -> bool:
        with self._session_factory() as session:
            if crud.agv_record.get(session, manufacturer, serial_number) is None:
                return False
            crud.agv_record.update(session, manufacturer, serial_number, **kwargs)
        return True

    def on_connect(self, agv_id: str) -> None:
        LOGGER.info("MQTT connect: %s", agv_id)

    def on_offline(self, agv_id: str) -> None:
        LOGGER.debug("MQTT offline: %s", agv_id)

    def on_connection_broken(self, agv_id: str) -> None:
        LOGGER.warning("Master-broker connection broken: %s", agv_id)

    def on_connection(self, agv_id: str, connection) -> None:
        mfr = connection.header.manufacturer
        sn = connection.header.serial_number
        is_online = connection.connection_state == ConnectionState.ONLINE

        if not is_online:
            self._pubs.pop(f"{mfr}/{sn}/state", None)
            self._pubs.pop(f"{mfr}/{sn}/factsheet", None)

        key = f"{mfr}/{sn}"
        if (
            self._heartbeat is not None
            and self._transport is not None
            and key not in self._heartbeat_registered
        ):
            pub = self._transport.create_publisher(
                Connection,
                self._full_topic(f"{mfr}/{sn}/connection"),
                delivery_mode=DeliveryMode.PERSISTENT,
            )

            def _publish_connection(
                m: str = mfr, s: str = sn, p: PublisherBase = pub
            ) -> None:
                agv = self._master.get_agv(m, s)
                if agv is None:
                    return
                conn = agv.get_last_connection()
                if conn is not None:
                    p.publish(conn)

            self._heartbeat.add(_publish_connection)
            self._heartbeat_registered.add(key)

        updated = self._update_if_registered(
            mfr,
            sn,
            is_online=is_online,
            connection_json=json.dumps(connection.json()),
            connection_updated_at=datetime.fromtimestamp(
                connection.header.timestamp, tz=timezone.utc
            ),
        )
        if not updated:
            LOGGER.info("Ignoring connection for unregistered AGV: %s", agv_id)
            return
        LOGGER.info("Connection updated: %s — %s", agv_id, connection.connection_state)

        if is_online:
            self._master.publish_instant_actions(mfr, sn, make_state_request(mfr, sn))
            self._master.publish_instant_actions(mfr, sn, make_factsheet_request(mfr, sn))

    def on_state(self, agv_id: str, state) -> None:
        mfr = state.header.manufacturer
        sn = state.header.serial_number

        state_pos = state.agv_position
        if state_pos is None:
            LOGGER.info("Waiting for agvPosition to be available %s...", agv_id)
        elif not state_pos.position_initialized:
            cfg = self._agv_configs.get(agv_id)
            LOGGER.info("Sending initPosition to %s", agv_id)
            instant_action = make_init_position(mfr, sn, cfg.init_config if cfg else None, state)
            self._master.publish_instant_actions(mfr, sn, instant_action)

        self._publish(State, f"{mfr}/{sn}/state", state)
        updated = self._update_if_registered(
            mfr,
            sn,
            state_json=json.dumps(state.json()),
            state_updated_at=datetime.fromtimestamp(
                state.header.timestamp, tz=timezone.utc
            ),
            active_order_id=state.order_id or None,
        )
        if not updated:
            LOGGER.debug("Ignoring state for unregistered AGV: %s", agv_id)
            return
        LOGGER.info("State updated: %s", agv_id)

    def on_order_complete(self, agv_id: str, order_id: str) -> None:
        manufacturer, serial_number = agv_id.split("/", 1)
        with self._session_factory() as session:
            r = crud.order_record.get_latest_by_order_id(
                session, manufacturer, serial_number, order_id
            )
            if r is not None:
                crud.order_record.update(
                    session,
                    db_obj=r,
                    obj_in={"completed_at": datetime.now(timezone.utc)},
                )
        LOGGER.info("Order completed: %s — %s", agv_id, order_id)

    def on_order_rejected(self, agv_id: str, order_id: str, errors) -> None:
        manufacturer, serial_number = agv_id.split("/", 1)
        with self._session_factory() as session:
            r = crud.order_record.get_latest_by_order_id(
                session, manufacturer, serial_number, order_id
            )
            if r is not None:
                crud.order_record.update(
                    session,
                    db_obj=r,
                    obj_in={
                        "rejected_at": datetime.now(timezone.utc),
                        "rejection_errors_json": json.dumps([e.json() for e in errors]),
                    },
                )
        LOGGER.warning("Order rejected: %s — %s", agv_id, order_id)

    def on_factsheet(self, agv_id: str, factsheet) -> None:
        mfr = factsheet.header.manufacturer
        sn = factsheet.header.serial_number
        self._publish(Factsheet, f"{mfr}/{sn}/factsheet", factsheet)
        updated = self._update_if_registered(
            mfr,
            sn,
            factsheet_json=json.dumps(factsheet.json()),
            factsheet_updated_at=datetime.fromtimestamp(
                factsheet.header.timestamp, tz=timezone.utc
            ),
        )
        if not updated:
            LOGGER.debug("Ignoring factsheet for unregistered AGV: %s", agv_id)
            return
        LOGGER.info("Factsheet updated: %s", agv_id)

    def on_visualization(self, agv_id: str, visualization) -> None:
        mfr = visualization.header.manufacturer
        sn = visualization.header.serial_number
        self._publish(Visualization, f"{mfr}/{sn}/visualization", visualization)
        LOGGER.debug("Visualization updated: %s", agv_id)


class _TransportObserver:
    """Wires inbound transport messages to master commands."""

    def __init__(
        self,
        master: VDA5050Master,
        transport: ServerTransportBase,
        topic_prefix: str | None = None,
    ) -> None:
        self._master = master

        def _full(topic: str) -> str:
            return f"{topic_prefix}/{topic}" if topic_prefix else topic

        self._order_result_pub = transport.create_publisher(
            OrderAssignmentResult, _full("assign_order_result")
        )
        self._instant_action_result_pub = transport.create_publisher(
            InstantActionsResult, _full("assign_instant_actions_result")
        )
        self._subscribers = [
            transport.create_subscriber(Order, _full("assign_order"), self.on_assign_order),
            transport.create_subscriber(
                OrderBatch, _full("assign_order_batch"), self.on_assign_order_batch
            ),
            transport.create_subscriber(
                InstantActions,
                _full("assign_instant_actions"),
                self.on_assign_instant_actions,
            ),
        ]

    def _publish_order_result(
        self, order: Order, result_model: OrderAssignmentResult
    ) -> None:
        self._order_result_pub.publish(
            OrderAssignmentResult(
                decision=result_model.decision,
                errors=result_model.errors,
                order=order,
            )
        )

    def on_assign_order(self, order: Order) -> None:
        mfr, sn = order.header.manufacturer, order.header.serial_number
        result = self._master.assign_order(mfr, sn, order)
        result_model = OrderAssignmentResult.from_vda5050(result)
        LOGGER.info("assign_order %s/%s: %s", mfr, sn, result_model.decision)
        self._publish_order_result(order, result_model)

    def on_assign_order_batch(self, batch: OrderBatch) -> None:
        for order in batch.orders:
            mfr, sn = order.header.manufacturer, order.header.serial_number
            result = self._master.assign_order(mfr, sn, order)
            result_model = OrderAssignmentResult.from_vda5050(result)
            LOGGER.info("assign_order_batch %s/%s: %s", mfr, sn, result_model.decision)
            self._publish_order_result(order, result_model)

    def on_assign_instant_actions(self, actions: InstantActions) -> None:
        mfr, sn = actions.header.manufacturer, actions.header.serial_number
        result = self._master.assign_instant_actions(mfr, sn, actions)
        result_model = InstantActionsResult.from_vda5050(result)
        LOGGER.info("assign_instant_actions %s/%s: %s", mfr, sn, result_model.decision)
        self._instant_action_result_pub.publish(
            InstantActionsResult(
                decision=result_model.decision,
                errors=result_model.errors,
                instant_actions=actions,
            )
        )


@contextmanager
def make_master(
    config: Settings,
    session_factory: sessionmaker[Session],
    transport: ServerTransportBase | None,
    topic_prefix: str | None = None,
    heartbeat: Heartbeat | None = None,
) -> Generator[VDA5050Master, None, None]:
    # --- Build master and register observer callbacks ---
    base_id = config.master_mqtt_client_id or "rmf2-vda5050-master"
    master_id = f"{base_id}-{os.getpid()}"
    LOGGER.info("Starting master %s", master_id)
    mqtt_client = create_mqtt_client(config.mqtt_broker, master_id)
    master = VDA5050Master.make(mqtt_client)
    observer = _MasterObserver(
        master,
        session_factory,
        transport,
        topic_prefix=topic_prefix,
        heartbeat=heartbeat,
        agv_configs=config.agvs,
    )
    _transport_observer = (
        _TransportObserver(master, transport, topic_prefix=topic_prefix)
        if transport is not None
        else None
    )

    master.on_connect(observer.on_connect)
    master.on_offline(observer.on_offline)
    master.on_connection_broken(observer.on_connection_broken)
    master.on_connection(observer.on_connection)
    master.on_state(observer.on_state)
    master.on_factsheet(observer.on_factsheet)
    master.on_visualization(observer.on_visualization)
    master.on_order_complete(observer.on_order_complete)
    master.on_order_rejected(observer.on_order_rejected)

    # --- Connect to MQTT broker ---
    LOGGER.info("Connecting to MQTT broker %s", config.mqtt_broker)
    master.connect()
    LOGGER.info("Connected to MQTT broker")

    # --- Load LIF layout (optional) ---
    _lif_json: str | None = None
    if config.map_mode == "local" and config.map_path is not None:
        _lif_json = config.map_path.read_text()
        result = master.load_layout_from_config(str(config.map_path))
        if result.get("errors"):
            LOGGER.warning(
                "Layout loaded with errors from %s: %s",
                config.map_path,
                result["errors"],
            )
        else:
            LOGGER.info("Layout loaded from %s", config.map_path)
    elif config.map_mode == "server" and config.map_server_url is not None:
        raise NotImplementedError(
            "Loading layout from an external map server is not yet implemented"
        )
    elif config.map_mode == "server" and config.map_server_url is None:
        LOGGER.warning(
            "map_mode is 'server' but map_server_url is not set — no layout loaded"
        )

    if _lif_json is not None:
        with session_factory() as session:
            crud.lif_record.set_current(session, _lif_json, datetime.now(timezone.utc))

    # --- Reset stale DB records from a previous (possibly crashed) session ---
    # Any AGV left as is_onboarded=True from a prior run is deleted so save_agv
    # can recreate them with a clean state below.
    with session_factory() as session:
        reset_ids = crud.agv_record.reset_all_onboarded(session)
        for agv_id in reset_ids:
            LOGGER.warning("Reset stale onboarded AGV on startup: %s", agv_id)

    # --- Create fresh DB records for all configured AGVs ---
    LOGGER.info("Initialising DB records for %d configured AGV(s)", len(config.agvs))
    with session_factory() as session:
        for agv in config.agvs:
            save_agv(session, agv.manufacturer, agv.serial_number)
            LOGGER.debug(
                "DB record ready for %s/%s", agv.manufacturer, agv.serial_number
            )

    # --- Onboard AGVs with the master ---
    # DB records are created first so that callbacks (on_connection, on_state, …)
    # can persist data as soon as the AGV connects.
    specs = []
    for agv in config.agvs:
        spec = OnboardSpec()
        spec.manufacturer = agv.manufacturer
        spec.serial_number = agv.serial_number
        specs.append(spec)

    result = master.onboard_agv_batch(specs)
    LOGGER.info(
        "Onboarded %d AGV(s), %d failed via %s",
        len(result.onboarded),
        len(result.failed),
        config.mqtt_broker,
    )
    for onboarded in result.onboarded:
        mfr, sn = onboarded.manufacturer, onboarded.serial_number
        master.publish_instant_actions(mfr, sn, make_state_request(mfr, sn))
        master.publish_instant_actions(mfr, sn, make_factsheet_request(mfr, sn))
        LOGGER.debug("Sent stateRequest + factsheetRequest after onboarding %s/%s", mfr, sn)
    if result.failed:
        with session_factory() as session:
            for failed in result.failed:
                LOGGER.error(
                    "Failed to onboard AGV: %s/%s",
                    failed.manufacturer,
                    failed.serial_number,
                )
                crud.agv_record.update(
                    session,
                    failed.manufacturer,
                    failed.serial_number,
                    is_onboarded=False,
                )

    LOGGER.info("Master ready")
    try:
        yield master
    finally:
        # --- Graceful shutdown: offboard all AGVs and mark DB records ---
        LOGGER.info("Shutting down master, offboarding %d AGV(s)", len(config.agvs))
        master.offboard_agv_batch(
            [(agv.manufacturer, agv.serial_number) for agv in config.agvs]
        )
        master.disconnect()
        LOGGER.info("Disconnected from MQTT broker")
        with session_factory() as session:
            for agv in config.agvs:
                crud.agv_record.update(
                    session,
                    agv.manufacturer,
                    agv.serial_number,
                    is_onboarded=False,
                )
