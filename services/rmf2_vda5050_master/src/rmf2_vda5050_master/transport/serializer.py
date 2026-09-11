from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SerializerBase(ABC):
    """Abstract serializer interface. Implement to plug in custom wire formats."""

    @abstractmethod
    def serialize(self, message: Any) -> str:
        """Encode ``message`` to a string for transport."""

    @abstractmethod
    def deserialize(self, body: str, message_type: type) -> Any:
        """Decode ``body`` string into an instance of ``message_type``."""
