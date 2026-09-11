"""Tests for transport/zenoh.py — mocks eclipse-zenoh to avoid a real router."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from rmf2_vda5050_master.transport.base import DeliveryMode
from rmf2_vda5050_master.transport.zenoh import (
    ServerTransportZenoh,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.declare_publisher.return_value = MagicMock()
    session.declare_subscriber.return_value = MagicMock()
    return session


@pytest.fixture
def transport(mock_session):
    with patch("rmf2_vda5050_master.transport.zenoh.zenoh") as mock_zenoh:
        mock_zenoh.open.return_value = mock_session
        mock_zenoh.Config.return_value = MagicMock()
        mock_zenoh.CongestionControl.DROP = "drop"
        mock_zenoh.CongestionControl.BLOCK = "block"
        mock_zenoh.ZError = RuntimeError
        t = ServerTransportZenoh()
        t._session = mock_session
        yield t


# ---------------------------------------------------------------------------
# ServerTransportZenoh — construction
# ---------------------------------------------------------------------------


def test_open_called_on_construction(mock_session):
    with patch("rmf2_vda5050_master.transport.zenoh.zenoh") as mock_zenoh:
        mock_zenoh.open.return_value = mock_session
        mock_zenoh.Config.return_value = MagicMock()
        mock_zenoh.CongestionControl.DROP = "drop"
        mock_zenoh.CongestionControl.BLOCK = "block"
        mock_zenoh.ZError = RuntimeError
        ServerTransportZenoh()
        mock_zenoh.open.assert_called_once()


def test_from_endpoints_inserts_config(mock_session):
    with patch("rmf2_vda5050_master.transport.zenoh.zenoh") as mock_zenoh:
        mock_config = MagicMock()
        mock_zenoh.Config.return_value = mock_config
        mock_zenoh.open.return_value = mock_session
        mock_zenoh.CongestionControl.DROP = "drop"
        mock_zenoh.CongestionControl.BLOCK = "block"
        mock_zenoh.ZError = RuntimeError

        endpoints = ["tcp/localhost:7447"]
        ServerTransportZenoh.from_endpoints(endpoints)

        mock_config.insert_json5.assert_called_once_with(
            "connect/endpoints", json.dumps(endpoints)
        )


# ---------------------------------------------------------------------------
# ZenohPublisher
# ---------------------------------------------------------------------------


def test_publisher_declares_on_session(transport, mock_session):
    transport.create_publisher(str, "my/topic")
    mock_session.declare_publisher.assert_called_once()
    args, _ = mock_session.declare_publisher.call_args
    assert args[0] == "my/topic"


def test_publisher_put_encodes_body(transport, mock_session):
    mock_pub = MagicMock()
    mock_session.declare_publisher.return_value = mock_pub

    pub = transport.create_publisher(str, "a/b")
    pub.publish("hello")

    mock_pub.put.assert_called_once_with(b"hello")


def test_publisher_transient_uses_drop(mock_session):
    with patch("rmf2_vda5050_master.transport.zenoh.zenoh") as mock_zenoh:
        mock_zenoh.CongestionControl.DROP = "drop"
        mock_zenoh.CongestionControl.BLOCK = "block"
        mock_zenoh.open.return_value = mock_session
        mock_zenoh.Config.return_value = MagicMock()
        mock_zenoh.ZError = RuntimeError

        t = ServerTransportZenoh()
        t._session = mock_session
        t.create_publisher(str, "t", delivery_mode=DeliveryMode.TRANSIENT)

        _, kwargs = mock_session.declare_publisher.call_args
        assert kwargs["congestion_control"] == "drop"


def test_publisher_persistent_uses_block(mock_session):
    with patch("rmf2_vda5050_master.transport.zenoh.zenoh") as mock_zenoh:
        mock_zenoh.CongestionControl.DROP = "drop"
        mock_zenoh.CongestionControl.BLOCK = "block"
        mock_zenoh.open.return_value = mock_session
        mock_zenoh.Config.return_value = MagicMock()
        mock_zenoh.ZError = RuntimeError

        t = ServerTransportZenoh()
        t._session = mock_session
        t.create_publisher(str, "t", delivery_mode=DeliveryMode.PERSISTENT)

        _, kwargs = mock_session.declare_publisher.call_args
        assert kwargs["congestion_control"] == "block"


def test_publisher_put_error_does_not_raise(transport, mock_session):
    mock_pub = MagicMock()
    mock_pub.put.side_effect = RuntimeError("zenoh error")
    mock_session.declare_publisher.return_value = mock_pub

    pub = transport.create_publisher(str, "t")
    pub.publish("msg")  # must not raise


# ---------------------------------------------------------------------------
# ZenohSubscriber
# ---------------------------------------------------------------------------


def test_subscribe_declares_on_session(transport, mock_session):
    transport.create_subscriber(str, "my/topic", lambda msg: None)
    mock_session.declare_subscriber.assert_called_once()
    args, _ = mock_session.declare_subscriber.call_args
    assert args[0] == "my/topic"


def test_subscriber_callback_invoked(transport, mock_session):
    received = []
    captured_handler = None

    def capture_handler(topic, handler):
        nonlocal captured_handler
        captured_handler = handler
        return MagicMock()

    mock_session.declare_subscriber.side_effect = capture_handler

    transport.create_subscriber(str, "t", lambda topic, body: received.append((topic, body)))

    sample = MagicMock()
    sample.key_expr = "t"
    sample.payload = b"hello"
    captured_handler(sample)

    assert received == [("t", "hello")]


def test_subscriber_unsubscribe_calls_undeclare(transport, mock_session):
    mock_sub = MagicMock()
    mock_session.declare_subscriber.return_value = mock_sub

    sub = transport.create_subscriber(str, "t", lambda msg: None)
    sub.unsubscribe()

    mock_sub.undeclare.assert_called_once()


def test_subscriber_unsubscribe_idempotent(transport, mock_session):
    mock_sub = MagicMock()
    mock_sub.undeclare.side_effect = RuntimeError("already closed")
    mock_session.declare_subscriber.return_value = mock_sub

    sub = transport.create_subscriber(str, "t", lambda msg: None)
    sub.unsubscribe()  # must not raise


# ---------------------------------------------------------------------------
# spin_once / spin_some
# ---------------------------------------------------------------------------


def test_spin_once_is_noop(transport):
    transport.spin_once(timeout=1.0)  # must not raise


def test_spin_some_is_noop(transport):
    transport.spin_some()  # must not raise


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


def test_close_closes_session(transport, mock_session):
    transport.close()
    mock_session.close.assert_called_once()


def test_close_error_does_not_raise(transport, mock_session):
    mock_session.close.side_effect = RuntimeError("session gone")
    transport.close()  # must not raise
