from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import IntEnum
from typing import Generic, TypeVar

from .json_serializer import JsonSerializer
from .serializer import SerializerBase

T = TypeVar("T")


class DeliveryMode(IntEnum):
    TRANSIENT = 1
    PERSISTENT = 2


# ---------------------------------------------------------------------------
# Publisher / Subscriber base classes
# ---------------------------------------------------------------------------


class PublisherBase(ABC, Generic[T]):
    """Abstract publisher bound to a single transport."""

    def __init__(self, topic: str, message_type: type[T]) -> None:
        self.topic = topic
        self.message_type = message_type

    @abstractmethod
    def publish(self, message: T) -> None:
        """Serialize and send ``message`` to the bound topic."""


class SubscriberBase:
    """Base subscriber handle. Subclasses may add transport-specific attributes."""

    def __init__(self, topic: str, message_type: type | None) -> None:
        self.topic = topic
        self.message_type = message_type


# ---------------------------------------------------------------------------
# Internal helper — shared by transport create_subscriber implementations
# ---------------------------------------------------------------------------


def make_raw_callback(
    callback: Callable,
    message_type: type,
    serializer: SerializerBase,
) -> Callable[[str, str], None]:
    """Wrap a typed callback into a raw ``(topic: str, body: str)`` callback."""
    two_arg = len(inspect.signature(callback).parameters) >= 2

    if message_type is str:
        return callback if two_arg else lambda t, body: callback(body)

    if two_arg:

        def raw(t: str, body: str) -> None:
            callback(t, serializer.deserialize(body, message_type))
    else:

        def raw(t: str, body: str) -> None:  # type: ignore[misc]
            callback(serializer.deserialize(body, message_type))

    return raw


# ---------------------------------------------------------------------------
# Base transport
# ---------------------------------------------------------------------------


class ServerTransportBase(ABC):
    """Wire transport interface (AMQP, Zenoh, …).

    Args:
        serializer: Serializer used for all publishers and subscribers created
            by this transport. Defaults to :class:`JsonSerializer`.

    Each subclass owns its connection lifecycle and fully implements
    :meth:`create_publisher` and :meth:`create_subscriber`.
    """

    def __init__(self, serializer: SerializerBase | None = None) -> None:
        self.serializer: SerializerBase = serializer or JsonSerializer()

    @abstractmethod
    def create_publisher(
        self,
        message_type: type[T],
        topic: str,
        *,
        delivery_mode: DeliveryMode = DeliveryMode.TRANSIENT,
    ) -> PublisherBase[T]:
        """Return a publisher bound to ``topic`` on this transport.

        Args:
            delivery_mode: Transport delivery mode. ``1`` = non-persistent,
                ``2`` = persistent (survives broker restart).
        """

    @abstractmethod
    def create_subscriber(
        self,
        message_type: type[T],
        topic: str,
        callback: Callable,
    ) -> SubscriberBase:
        """Register ``callback`` for ``topic`` and return a subscriber handle.

        Args:
            message_type: Deserialization target. Pass ``str`` for raw body.
            topic: Topic / pattern string (transport's own wildcard syntax).
            callback: Accepted signatures::

                    def handler(message: T) -> None: ...
                    def handler(topic: str, message: T) -> None: ...
        """

    @property
    def needs_spin(self) -> bool:
        """Return ``True`` if this transport requires an external spin loop.

        Transports that run their own I/O thread (e.g. :class:`ServerTransportAmqp`)
        return ``False`` so the executor does not spawn a redundant spin thread.
        """
        return True

    @abstractmethod
    def spin_once(self, timeout: float = 0.0) -> None:
        """Process I/O and dispatch callbacks, blocking for up to ``timeout`` seconds."""

    @abstractmethod
    def spin_some(self) -> None:
        """Process all currently pending I/O and callbacks without blocking."""
