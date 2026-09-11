from __future__ import annotations

import json
from collections.abc import Callable
from typing import TypeVar

import zenoh

from ..logger import get_logger
from .base import (
    DeliveryMode,
    PublisherBase,
    ServerTransportBase,
    SubscriberBase,
    make_raw_callback,
)
from .serializer import SerializerBase

LOGGER = get_logger(__name__)

T = TypeVar("T")


class ZenohPublisher(PublisherBase[T]):
    """Publisher that serializes and sends via a :class:`ServerTransportZenoh`."""

    def __init__(
        self,
        topic: str,
        message_type: type[T],
        serializer: SerializerBase,
        session: zenoh.Session,
        *,
        delivery_mode: DeliveryMode = DeliveryMode.TRANSIENT,
    ) -> None:
        super().__init__(topic, message_type)
        self._serializer = serializer
        congestion_control = (
            zenoh.CongestionControl.BLOCK
            if delivery_mode == DeliveryMode.PERSISTENT
            else zenoh.CongestionControl.DROP
        )
        self._pub = session.declare_publisher(
            topic, congestion_control=congestion_control
        )

    def publish(self, message: T) -> None:
        body = self._serializer.serialize(message)
        try:
            self._pub.put(body.encode())
        except zenoh.ZError as exc:
            LOGGER.warning(
                "ZenohPublisher.publish failed for '%s': %s", self.topic, exc
            )

    def __del__(self) -> None:
        pub, self._pub = self._pub, None
        if pub is None:
            return
        try:
            pub.undeclare()
        except zenoh.ZError:
            pass


class ZenohSubscriber(SubscriberBase):
    """Subscriber handle for Zenoh. Undeclares its subscriber on GC or explicit close."""

    def __init__(
        self,
        topic: str,
        message_type: type | None,
        session: zenoh.Session,
        raw_callback: Callable[[str, str], None],
    ) -> None:
        super().__init__(topic, message_type)

        def _handler(sample: zenoh.Sample) -> None:
            key = str(sample.key_expr)
            try:
                body = bytes(sample.payload).decode()
                raw_callback(key, body)
            except Exception as exc:  # noqa: BLE001 — user callback may raise anything
                LOGGER.error("Handler error for topic '%s': %s", key, exc)

        self._sub = session.declare_subscriber(topic, _handler)

    def unsubscribe(self) -> None:
        sub, self._sub = self._sub, None
        if sub is None:
            return
        try:
            sub.undeclare()
        except zenoh.ZError:
            pass

    def __del__(self) -> None:
        self.unsubscribe()


class ServerTransportZenoh(ServerTransportBase):
    """Zenoh transport backed by ``eclipse-zenoh``.

    Zenoh uses ``/``-separated key expressions natively, so no topic conversion
    is needed. Callbacks are delivered on Zenoh's internal thread.

    ::

        transport = ServerTransportZenoh()                              # default config
        transport = ServerTransportZenoh.from_endpoints(["tcp/localhost:7447"])

    Zenoh reconnects to endpoints automatically; :meth:`spin_once` and
    :meth:`spin_some` are no-ops.
    """

    def __init__(
        self,
        config: zenoh.Config | None = None,
        *,
        serializer: SerializerBase | None = None,
    ) -> None:
        super().__init__(serializer=serializer)
        self._config = config or zenoh.Config()
        self._session: zenoh.Session = zenoh.open(self._config)
        LOGGER.info("Zenoh session opened")

    @classmethod
    def from_endpoints(cls, endpoints: list[str], **kwargs) -> ServerTransportZenoh:
        """Open a Zenoh session connected to ``endpoints`` (e.g. ``["tcp/localhost:7447"]``)."""
        config = zenoh.Config()
        config.insert_json5("connect/endpoints", json.dumps(endpoints))
        return cls(config, **kwargs)

    def create_publisher(
        self,
        message_type: type[T],
        topic: str,
        *,
        delivery_mode: DeliveryMode = DeliveryMode.TRANSIENT,
    ) -> ZenohPublisher[T]:
        return ZenohPublisher(
            topic,
            message_type,
            self.serializer,
            self._session,
            delivery_mode=delivery_mode,
        )

    def create_subscriber(
        self,
        message_type: type[T],
        topic: str,
        callback: Callable,
    ) -> ZenohSubscriber:
        raw = make_raw_callback(callback, message_type, self.serializer)
        return ZenohSubscriber(topic, message_type, self._session, raw)

    def spin_once(self, timeout: float = 0.0) -> None:
        pass  # Zenoh dispatches callbacks on its own internal thread

    def spin_some(self) -> None:
        pass  # Zenoh dispatches callbacks on its own internal thread

    def close(self) -> None:
        """Close the Zenoh session."""
        try:
            self._session.close()
        except zenoh.ZError as exc:
            LOGGER.warning("Zenoh session close error: %s", exc)
