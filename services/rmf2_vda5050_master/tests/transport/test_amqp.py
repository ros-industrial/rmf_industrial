"""Tests for transport/amqp.py — mocks pika to avoid a real broker."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest
from pika import ConnectionParameters
from pika.channel import Channel
from pika.exchange_type import ExchangeType

from rmf2_vda5050_master.transport.amqp import (
    AmqpPublisher,
    AmqpSubscriber,
    ServerTransportAmqp,
    _make_handler,
    _to_amqp_routing_key,
)
from rmf2_vda5050_master.transport.base import DeliveryMode
from rmf2_vda5050_master.transport.json_serializer import JsonSerializer

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_ioloop():
    loop = MagicMock()
    loop.add_callback_threadsafe.side_effect = lambda fn: fn()
    return loop


@pytest.fixture
def mock_channel():
    ch = MagicMock(spec=Channel)
    ch.is_open = True
    result = MagicMock()
    result.method.queue = "test-queue"
    ch.basic_consume.return_value = "consumer-tag-1"
    return ch


@pytest.fixture
def mock_connection(mock_channel, mock_ioloop):
    conn = MagicMock()
    conn.is_open = True
    conn.ioloop = mock_ioloop
    return conn


@pytest.fixture
def transport(mock_connection, mock_channel):
    """Transport with auto_connect=False, connection and channel injected."""
    t = ServerTransportAmqp(
        ConnectionParameters("localhost"), "test-exchange", auto_connect=False
    )
    t._connection = mock_connection
    t._channel = mock_channel
    return t


# ---------------------------------------------------------------------------
# _to_amqp_routing_key
# ---------------------------------------------------------------------------


def test_routing_key_replaces_slashes():
    assert _to_amqp_routing_key("foo/bar/baz") == "foo.bar.baz"


def test_routing_key_no_slashes():
    assert _to_amqp_routing_key("foo") == "foo"


# ---------------------------------------------------------------------------
# _make_handler
# ---------------------------------------------------------------------------


def test_make_handler_invokes_callback():
    received = []
    raw = lambda t, body: received.append((t, body))
    handler = _make_handler(raw)

    ch = MagicMock()
    method = MagicMock()
    method.routing_key = "foo.bar"
    method.delivery_tag = 1

    handler(ch, method, None, b'{"x":1}')

    assert received == [("foo/bar", '{"x":1}')]
    ch.basic_ack.assert_called_once_with(delivery_tag=1)


def test_make_handler_acks_on_callback_error():
    def bad_callback(t, body):
        raise RuntimeError("oops")

    handler = _make_handler(bad_callback)
    ch = MagicMock()
    method = MagicMock()
    method.routing_key = "a.b"
    method.delivery_tag = 42

    handler(ch, method, None, b"body")

    ch.basic_ack.assert_called_once_with(delivery_tag=42)


# ---------------------------------------------------------------------------
# AmqpPublisher
# ---------------------------------------------------------------------------


def test_amqp_publisher_calls_send(transport, mock_channel):
    pub = transport.create_publisher(str, "my/topic")
    pub.publish("hello")

    mock_channel.basic_publish.assert_called_once()
    _, kwargs = mock_channel.basic_publish.call_args
    assert kwargs["routing_key"] == "my.topic"
    assert kwargs["body"] == b"hello"


def test_amqp_publisher_transient_delivery_mode(transport, mock_channel):
    pub = transport.create_publisher(str, "t", delivery_mode=DeliveryMode.TRANSIENT)
    pub.publish("msg")

    _, kwargs = mock_channel.basic_publish.call_args
    assert kwargs["properties"].delivery_mode == 1


def test_amqp_publisher_persistent_delivery_mode(transport, mock_channel):
    pub = transport.create_publisher(str, "t", delivery_mode=DeliveryMode.PERSISTENT)
    pub.publish("msg")

    _, kwargs = mock_channel.basic_publish.call_args
    assert kwargs["properties"].delivery_mode == 2


def test_amqp_publisher_dropped_when_transport_gone(mock_connection):
    transport = ServerTransportAmqp(
        ConnectionParameters("localhost"), "ex", auto_connect=False
    )
    transport._connection = mock_connection
    transport._channel = MagicMock(spec=Channel, is_open=True)
    pub = AmqpPublisher(transport, "topic", str, JsonSerializer())

    del transport
    pub.publish("msg")  # must not raise; weakref resolves to None

    mock_connection.ioloop.add_callback_threadsafe.assert_not_called()


# ---------------------------------------------------------------------------
# AmqpSubscriber
# ---------------------------------------------------------------------------


def test_amqp_subscriber_unsubscribe_clears_tag(transport):
    sub = AmqpSubscriber("t", str, "t", transport)
    sub.consumer_tag = "tag-99"

    sub.unsubscribe()

    assert sub.consumer_tag is None


def test_amqp_subscriber_unsubscribe_idempotent(transport):
    sub = AmqpSubscriber("t", str, "t", transport)
    sub.consumer_tag = None
    sub.unsubscribe()  # must not raise


# ---------------------------------------------------------------------------
# create_subscriber — registers and auto-binds when channel is open
# ---------------------------------------------------------------------------


def test_subscribe_appends_to_subscriptions(transport):
    assert len(transport._subscriptions) == 0
    transport.create_subscriber(str, "x", lambda msg: None)
    assert len(transport._subscriptions) == 1


def test_subscribe_schedules_bind_when_channel_ready(transport, mock_connection):
    transport.create_subscriber(str, "x", lambda msg: None)
    mock_connection.ioloop.add_callback_threadsafe.assert_called_once()


def test_subscribe_does_not_schedule_bind_without_channel(mock_connection):
    t = ServerTransportAmqp(ConnectionParameters("localhost"), "ex", auto_connect=False)
    t._connection = mock_connection
    t._channel = None  # no channel yet

    t.create_subscriber(str, "x", lambda msg: None)

    mock_connection.ioloop.add_callback_threadsafe.assert_not_called()


# ---------------------------------------------------------------------------
# Connection callbacks
# ---------------------------------------------------------------------------


def test_on_connected_opens_channel(transport, mock_connection):
    transport._on_connected(mock_connection)
    mock_connection.channel.assert_called_once()


def test_on_channel_open_declares_exchange(transport, mock_connection):
    channel = MagicMock(spec=Channel, is_open=True)
    transport._channel = None
    transport._on_channel_open(channel)

    assert transport._channel is channel
    channel.exchange_declare.assert_called_once_with(
        exchange="test-exchange",
        exchange_type=ExchangeType.topic,
        durable=True,
        callback=transport._on_exchange_declared,
    )


def test_on_exchange_declared_binds_all_subscribers(transport, mock_channel):
    # Subscribe before channel is available so no auto-bind fires.
    transport._channel = None
    transport.create_subscriber(str, "foo/bar", lambda msg: None)
    transport._channel = mock_channel

    transport._on_exchange_declared(MagicMock())

    mock_channel.queue_declare.assert_called_once()


def test_on_open_error_clears_connection(transport, mock_connection):
    transport._on_open_error(mock_connection, Exception("refused"))

    assert transport._connection is None


def test_on_closed_clears_channel_and_connection(transport, mock_connection):
    transport._on_closed(mock_connection, Exception("gone"))

    assert transport._channel is None
    assert transport._connection is None


def test_on_closed_stops_ioloop(transport, mock_connection):
    transport._on_closed(mock_connection, Exception("gone"))
    mock_connection.ioloop.stop.assert_called_once()


def test_on_open_error_stops_ioloop(transport, mock_connection):
    transport._on_open_error(mock_connection, Exception("refused"))
    mock_connection.ioloop.stop.assert_called_once()


def test_on_channel_closed_closes_connection(transport, mock_connection, mock_channel):
    transport._on_channel_closed(mock_channel, Exception("closed"))

    assert transport._channel is None
    mock_connection.close.assert_called_once()


# ---------------------------------------------------------------------------
# Consumer binding chain
# ---------------------------------------------------------------------------


def test_bind_subscriber_declares_queue(transport, mock_channel):
    sub = AmqpSubscriber("foo/bar", str, "foo.bar", transport)

    transport._bind_subscriber(sub, lambda t, b: None)

    mock_channel.queue_declare.assert_called_once()
    _, kwargs = mock_channel.queue_declare.call_args
    assert kwargs["queue"] == ""
    assert kwargs["exclusive"] is True
    assert callable(kwargs["callback"])


def test_bind_subscriber_skips_when_channel_closed(transport, mock_channel):
    mock_channel.is_open = False
    sub = AmqpSubscriber("t", str, "t", transport)
    transport._bind_subscriber(sub, lambda t, b: None)
    mock_channel.queue_declare.assert_not_called()


def test_on_queue_declared_binds_queue(transport, mock_channel):
    sub = AmqpSubscriber("foo/bar", str, "foo.bar", transport)
    result = MagicMock()
    result.method.queue = "q-1"

    transport._on_queue_declared(result, sub, lambda t, b: None)

    mock_channel.queue_bind.assert_called_once()
    _, kwargs = mock_channel.queue_bind.call_args
    assert kwargs["routing_key"] == "foo.bar"
    assert kwargs["queue"] == "q-1"


def test_on_queue_bound_starts_consumer(transport, mock_channel):
    sub = AmqpSubscriber("t", str, "t", transport)
    transport._on_queue_bound("q-1", sub, lambda t, b: None)

    mock_channel.basic_consume.assert_called_once()
    assert sub.consumer_tag == "consumer-tag-1"


# ---------------------------------------------------------------------------
# _send
# ---------------------------------------------------------------------------


def test_send_dropped_when_not_connected():
    t = ServerTransportAmqp(ConnectionParameters("localhost"), "ex", auto_connect=False)
    t._connection = None
    t._send("foo", "body")  # must not raise


def test_send_dropped_when_connection_closed(mock_connection):
    mock_connection.is_open = False
    t = ServerTransportAmqp(ConnectionParameters("localhost"), "ex", auto_connect=False)
    t._connection = mock_connection
    t._send("foo", "body")
    mock_connection.ioloop.add_callback_threadsafe.assert_not_called()


def test_send_uses_correct_routing_key(transport, mock_channel):
    transport._send("a/b/c", "body")

    _, kwargs = mock_channel.basic_publish.call_args
    assert kwargs["routing_key"] == "a.b.c"


def test_send_content_type_is_json(transport, mock_channel):
    transport._send("t", "body")

    _, kwargs = mock_channel.basic_publish.call_args
    assert kwargs["properties"].content_type == "application/json"


# ---------------------------------------------------------------------------
# Thread safety — create_subscriber
# ---------------------------------------------------------------------------


def test_subscribe_thread_safety():
    t = ServerTransportAmqp(ConnectionParameters("localhost"), "ex", auto_connect=False)
    errors: list[Exception] = []
    n = 40
    barrier = threading.Barrier(n)

    def worker(i: int):
        barrier.wait()
        try:
            t.create_subscriber(str, f"topic/{i}", lambda msg: None)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert errors == []
    assert len(t._subscriptions) == n
