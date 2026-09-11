"""Tests for transport/base.py and transport/json_serializer.py."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from rmf2_vda5050_master.transport.base import (
    DeliveryMode,
    PublisherBase,
    ServerTransportBase,
    SubscriberBase,
    make_raw_callback,
)
from rmf2_vda5050_master.transport.json_serializer import JsonSerializer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeTransport(ServerTransportBase):
    def create_publisher(
        self, message_type, topic, *, delivery_mode=DeliveryMode.TRANSIENT
    ):
        return _FakePublisher(topic, message_type)

    def create_subscriber(self, message_type, topic, callback):
        return SubscriberBase(topic, message_type)

    def spin_once(self, timeout=0.0):
        pass

    def spin_some(self):
        pass


class _FakePublisher(PublisherBase):
    def __init__(self, topic, message_type):
        super().__init__(topic, message_type)
        self.published = []

    def publish(self, message):
        self.published.append(message)


class _JsonModel(BaseModel):
    value: int


class _LegacyModel:
    def __init__(self, x: int):
        self.x = x

    def json(self):
        return {"x": self.x}

    @classmethod
    def from_json(cls, data: dict):
        return cls(data["x"])


# ---------------------------------------------------------------------------
# DeliveryMode
# ---------------------------------------------------------------------------


def test_delivery_mode_values():
    assert DeliveryMode.TRANSIENT == 1
    assert DeliveryMode.PERSISTENT == 2


def test_delivery_mode_is_int():
    assert isinstance(DeliveryMode.TRANSIENT, int)
    assert isinstance(DeliveryMode.PERSISTENT, int)


# ---------------------------------------------------------------------------
# make_raw_callback
# ---------------------------------------------------------------------------


def test_make_raw_callback_one_arg_deserializes():
    serializer = JsonSerializer()
    received = []

    def handler(msg: _JsonModel):
        received.append(msg)

    raw = make_raw_callback(handler, _JsonModel, serializer)
    raw("topic", '{"value": 42}')

    assert len(received) == 1
    assert received[0].value == 42


def test_make_raw_callback_two_arg_receives_topic():
    serializer = JsonSerializer()
    received = []

    def handler(topic: str, msg: _JsonModel):
        received.append((topic, msg))

    raw = make_raw_callback(handler, _JsonModel, serializer)
    raw("my/topic", '{"value": 7}')

    assert received[0] == ("my/topic", _JsonModel(value=7))


def test_make_raw_callback_str_passthrough_one_arg():
    serializer = JsonSerializer()
    received = []

    raw = make_raw_callback(lambda body: received.append(body), str, serializer)
    raw("t", "hello")

    assert received == ["hello"]


def test_make_raw_callback_str_passthrough_two_arg():
    serializer = JsonSerializer()
    received = []

    raw = make_raw_callback(lambda t, body: received.append((t, body)), str, serializer)
    raw("t", "hello")

    assert received == [("t", "hello")]


def test_make_raw_callback_legacy_from_json():
    serializer = JsonSerializer()
    received = []

    def handler(msg: _LegacyModel):
        received.append(msg)

    raw = make_raw_callback(handler, _LegacyModel, serializer)
    raw("t", '{"x": 99}')

    assert received[0].x == 99


# ---------------------------------------------------------------------------
# JsonSerializer
# ---------------------------------------------------------------------------


def test_json_serializer_pydantic_round_trip():
    s = JsonSerializer()
    msg = _JsonModel(value=5)
    body = s.serialize(msg)
    out = s.deserialize(body, _JsonModel)
    assert out == msg


def test_json_serializer_legacy_round_trip():
    s = JsonSerializer()
    msg = _LegacyModel(42)
    body = s.serialize(msg)
    out = s.deserialize(body, _LegacyModel)
    assert out.x == 42


def test_json_serializer_str_passthrough():
    s = JsonSerializer()
    assert s.serialize("raw") == "raw"
    assert s.deserialize("raw", str) == "raw"


def test_json_serializer_unknown_type_raises():
    s = JsonSerializer()
    with pytest.raises(TypeError):
        s.serialize(object())
