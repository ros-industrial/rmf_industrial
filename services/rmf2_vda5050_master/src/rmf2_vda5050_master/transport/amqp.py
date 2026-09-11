from __future__ import annotations

import threading
import weakref
from collections.abc import Callable
from typing import TypeVar

from pika import BasicProperties, ConnectionParameters, URLParameters
from pika.adapters.select_connection import SelectConnection
from pika.channel import Channel
from pika.exceptions import AMQPError
from pika.exchange_type import ExchangeType

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


def _to_amqp_routing_key(topic: str) -> str:
    """Convert MQTT-style topic (/ separator) to AMQP routing key (. separator)."""
    return topic.replace("/", ".")


# ---------------------------------------------------------------------------
# AMQP publisher
# ---------------------------------------------------------------------------


class AmqpPublisher(PublisherBase[T]):
    """Publisher that serializes and sends via a :class:`ServerTransportAmqp`."""

    def __init__(
        self,
        transport: ServerTransportAmqp,
        topic: str,
        message_type: type[T],
        serializer: SerializerBase,
        *,
        delivery_mode: DeliveryMode = DeliveryMode.TRANSIENT,
    ) -> None:
        super().__init__(topic, message_type)
        self._transport_ref: weakref.ref[ServerTransportAmqp] = weakref.ref(transport)
        self._serializer = serializer
        self._delivery_mode = delivery_mode

    def publish(self, message: T) -> None:
        transport = self._transport_ref()
        if transport is None:
            LOGGER.warning(
                "AmqpPublisher.publish dropped (transport destroyed): %s", self.topic
            )
            return
        body = self._serializer.serialize(message)
        transport._send(self.topic, body, delivery_mode=self._delivery_mode)


# ---------------------------------------------------------------------------
# AMQP subscriber
# ---------------------------------------------------------------------------


class AmqpSubscriber(SubscriberBase):
    """Subscriber handle for AMQP.

    Cancels its AMQP consumer when it is garbage-collected or when
    :meth:`unsubscribe` is called explicitly.
    """

    def __init__(
        self,
        topic: str,
        message_type: type | None,
        routing_key: str,
        transport: ServerTransportAmqp,
    ) -> None:
        super().__init__(topic, message_type)
        self.routing_key = routing_key
        self.consumer_tag: str | None = None
        self._transport_ref: weakref.ref[ServerTransportAmqp] = weakref.ref(transport)

    def unsubscribe(self) -> None:
        """Cancel the AMQP consumer immediately."""
        transport = self._transport_ref()
        if transport is not None and self.consumer_tag is not None:
            transport._cancel_consumer(self.consumer_tag)
            self.consumer_tag = None

    def __del__(self) -> None:
        self.unsubscribe()


# ---------------------------------------------------------------------------
# AMQP transport
# ---------------------------------------------------------------------------


class ServerTransportAmqp(ServerTransportBase):
    """AMQP transport using a topic exchange and :class:`SelectConnection`.

    Topics use MQTT-style ``/`` separators; converted to ``.`` for AMQP routing keys.
    Each :meth:`create_subscriber` call gets its own exclusive queue.

    Pass a :class:`~pika.ConnectionParameters` (or :class:`~pika.URLParameters`);
    the transport manages its own connection and reconnects automatically::

        transport = ServerTransportAmqp(ConnectionParameters("localhost"), "rmf2")
        # or from a URL:
        transport = ServerTransportAmqp.from_url("amqp://localhost", "rmf2")

    A dedicated daemon thread runs the :class:`SelectConnection` ioloop.
    Connection errors and broker-initiated closes trigger automatic reconnection
    after ``retry_interval`` seconds via ``on_open_error_callback`` and
    ``on_close_callback``.

    :meth:`spin_once` and :meth:`spin_some` are no-ops — the ioloop is self-driving.
    :meth:`_send` and :meth:`_cancel_consumer` are thread-safe via
    ``ioloop.add_callback_threadsafe``.

    """

    def __init__(
        self,
        params: ConnectionParameters,
        exchange: str,
        *,
        prefetch_count: int = 1,
        retry_interval: float = 5.0,
        auto_connect: bool = True,
        serializer: SerializerBase | None = None,
    ) -> None:
        super().__init__(serializer=serializer)
        self._params = params
        self._exchange = exchange
        self._prefetch_count = prefetch_count
        self._retry_interval = retry_interval
        self._connection: SelectConnection | None = None
        self._channel: Channel | None = None
        # (subscriber, raw_callback) — consumer_tag filled in when channel is ready
        self._subscriptions: list[
            tuple[AmqpSubscriber, Callable[[str, str], None]]
        ] = []
        self._subscriptions_lock = threading.Lock()
        self._running = False
        self._stop_event = threading.Event()
        self._ioloop_thread: threading.Thread | None = None

        if auto_connect:
            self._start()

    # ------------------------------------------------------------------
    # Alternative constructor
    # ------------------------------------------------------------------

    @classmethod
    def from_url(cls, url: str, exchange: str, **kwargs) -> ServerTransportAmqp:
        """Create a transport from a URL string.

        Parses ``url`` into :class:`~pika.URLParameters` and delegates to
        :class:`ServerTransportAmqp`. Remaining ``kwargs`` are forwarded to ``__init__``.
        """
        return cls(URLParameters(url), exchange, **kwargs)

    # ------------------------------------------------------------------
    # ServerTransportBase — typed pub/sub
    # ------------------------------------------------------------------

    def create_publisher(
        self,
        message_type: type[T],
        topic: str,
        *,
        delivery_mode: DeliveryMode = DeliveryMode.TRANSIENT,
    ) -> AmqpPublisher[T]:
        return AmqpPublisher(
            self, topic, message_type, self.serializer, delivery_mode=delivery_mode
        )

    def create_subscriber(
        self,
        message_type: type[T],
        topic: str,
        callback: Callable,
    ) -> AmqpSubscriber:
        raw = make_raw_callback(callback, message_type, self.serializer)
        subscriber = AmqpSubscriber(
            topic, message_type, _to_amqp_routing_key(topic), self
        )
        with self._subscriptions_lock:
            self._subscriptions.append((subscriber, raw))
        # If channel is already open, bind the consumer immediately on the ioloop thread.
        conn = self._connection
        if conn is not None and self._channel is not None:
            conn.ioloop.add_callback_threadsafe(
                lambda: self._bind_subscriber(subscriber, raw)
            )
        return subscriber

    # ------------------------------------------------------------------
    # Spin — no-ops; the ioloop runs in its own thread
    # ------------------------------------------------------------------

    @property
    def needs_spin(self) -> bool:
        return False

    def spin_once(self, timeout: float = 0.0) -> None:
        pass

    def spin_some(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def _start(self) -> None:
        """Start the ioloop daemon thread."""
        if self._ioloop_thread is not None and self._ioloop_thread.is_alive():
            return
        self._running = True
        self._stop_event.clear()
        self._ioloop_thread = threading.Thread(
            target=self._run, daemon=True, name="amqp-ioloop"
        )
        self._ioloop_thread.start()

    def _run(self) -> None:
        """Ioloop thread: connect, run, and reconnect on close."""
        while self._running:
            try:
                self._connection = SelectConnection(
                    self._params,
                    on_open_callback=self._on_connected,
                    on_open_error_callback=self._on_open_error,
                    on_close_callback=self._on_closed,
                )
                self._connection.ioloop.start()
            except Exception as exc:  # noqa: BLE001 — ioloop thread must survive any error
                LOGGER.warning("AMQP ioloop error: %s", exc)
                self._connection = None
                self._channel = None

            if self._running:
                self._stop_event.wait(timeout=self._retry_interval)
                self._stop_event.clear()

    def disconnect(self) -> None:
        """Stop the ioloop thread and close the connection."""
        self._running = False
        self._stop_event.set()
        conn = self._connection
        if conn is not None:
            conn.ioloop.add_callback_threadsafe(conn.close)
        if self._ioloop_thread is not None and self._ioloop_thread.is_alive():
            self._ioloop_thread.join(timeout=10.0)
        self._channel = None
        self._connection = None

    # ------------------------------------------------------------------
    # SelectConnection callbacks — run on the ioloop thread
    # ------------------------------------------------------------------

    def _on_connected(self, connection: SelectConnection) -> None:
        connection.channel(on_open_callback=self._on_channel_open)

    def _on_channel_open(self, channel: Channel) -> None:
        self._channel = channel
        channel.add_on_close_callback(self._on_channel_closed)
        channel.exchange_declare(
            exchange=self._exchange,
            exchange_type=ExchangeType.topic,
            durable=True,
            callback=self._on_exchange_declared,
        )

    def _on_exchange_declared(self, _frame) -> None:
        LOGGER.info("AMQP connected — exchange '%s'", self._exchange)
        with self._subscriptions_lock:
            subscriptions = list(self._subscriptions)
        for subscriber, raw in subscriptions:
            self._bind_subscriber(subscriber, raw)

    def _on_channel_closed(self, channel: Channel, reason: Exception) -> None:
        LOGGER.warning("AMQP channel closed: %s", reason)
        self._channel = None
        conn = self._connection
        if conn is not None and conn.is_open:
            conn.close()

    def _on_open_error(self, connection: SelectConnection, error: Exception) -> None:
        LOGGER.warning(
            "AMQP connection failed, retrying in %.1fs: %s", self._retry_interval, error
        )
        self._connection = None
        connection.ioloop.stop()

    def _on_closed(self, connection: SelectConnection, reason: Exception) -> None:
        self._channel = None
        self._connection = None
        LOGGER.warning(
            "AMQP connection closed, retrying in %.1fs: %s",
            self._retry_interval,
            reason,
        )
        connection.ioloop.stop()

    # ------------------------------------------------------------------
    # Consumer binding — called on the ioloop thread
    # ------------------------------------------------------------------

    def _bind_subscriber(self, subscriber: AmqpSubscriber, raw: Callable) -> None:
        """Declare an exclusive queue and start consuming. Runs on the ioloop thread."""
        channel = self._channel
        if channel is None or not channel.is_open:
            return
        channel.queue_declare(
            queue="",
            exclusive=True,
            callback=lambda result: self._on_queue_declared(result, subscriber, raw),
        )

    def _on_queue_declared(
        self, result, subscriber: AmqpSubscriber, raw: Callable
    ) -> None:
        queue_name = result.method.queue
        channel = self._channel
        if channel is None or not channel.is_open:
            return
        channel.queue_bind(
            exchange=self._exchange,
            queue=queue_name,
            routing_key=subscriber.routing_key,
            callback=lambda _: self._on_queue_bound(queue_name, subscriber, raw),
        )

    def _on_queue_bound(
        self, queue_name: str, subscriber: AmqpSubscriber, raw: Callable
    ) -> None:
        channel = self._channel
        if channel is None or not channel.is_open:
            return
        channel.basic_qos(prefetch_count=self._prefetch_count)
        consumer_tag = channel.basic_consume(
            queue=queue_name,
            on_message_callback=_make_handler(raw),
            auto_ack=False,
        )
        subscriber.consumer_tag = consumer_tag

    # ------------------------------------------------------------------
    # Internal — thread-safe send / cancel
    # ------------------------------------------------------------------

    def _send(
        self,
        topic: str,
        body: str,
        *,
        delivery_mode: DeliveryMode = DeliveryMode.TRANSIENT,
    ) -> None:
        """Thread-safe publish. ``topic`` uses MQTT-style / separators."""
        conn = self._connection
        if conn is None or not conn.is_open:
            LOGGER.warning("AMQP send dropped (not connected): %s", topic)
            return
        routing_key = _to_amqp_routing_key(topic)
        encoded = body.encode()
        props = BasicProperties(
            content_type="application/json",
            delivery_mode=2 if delivery_mode == DeliveryMode.PERSISTENT else 1,
        )

        def _do() -> None:
            ch = self._channel
            if ch is not None and ch.is_open:
                ch.basic_publish(
                    exchange=self._exchange,
                    routing_key=routing_key,
                    body=encoded,
                    properties=props,
                )

        conn.ioloop.add_callback_threadsafe(_do)

    def _cancel_consumer(self, consumer_tag: str) -> None:
        """Thread-safe consumer cancellation."""
        conn = self._connection
        if conn is None:
            return

        def _do() -> None:
            ch = self._channel
            if ch is not None and ch.is_open:
                try:
                    ch.basic_cancel(consumer_tag)
                except AMQPError as exc:
                    LOGGER.warning(
                        "Failed to cancel consumer '%s': %s", consumer_tag, exc
                    )

        conn.ioloop.add_callback_threadsafe(_do)


def _make_handler(callback: Callable[[str, str], None]) -> Callable:
    """Wrap a raw callback as a pika on_message_callback."""

    def handler(channel: Channel, method, _properties, body: bytes) -> None:
        topic = method.routing_key.replace(".", "/")
        try:
            callback(topic, body.decode())
        except Exception as exc:  # noqa: BLE001 — user callback may raise anything
            LOGGER.error("Handler error for topic '%s': %s", topic, exc)
        channel.basic_ack(delivery_tag=method.delivery_tag)

    return handler
