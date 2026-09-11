from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from .serializer import SerializerBase


class JsonSerializer(SerializerBase):
    """JSON serializer backed by pydantic ``BaseModel`` or the ``json`` module."""

    def serialize(self, message: Any) -> str:
        if isinstance(message, str):
            return message
        if isinstance(message, BaseModel):
            return message.model_dump_json()
        if callable(getattr(message, "json", None)):
            return json.dumps(message.json())
        raise TypeError(
            f"Cannot serialize {type(message).__name__!r} for transport publish"
        )

    def deserialize(self, body: str, message_type: type) -> Any:
        if message_type is str:
            return body
        if issubclass(message_type, BaseModel):
            return message_type.model_validate_json(body)
        if hasattr(message_type, "from_json"):
            return message_type.from_json(json.loads(body))
        raise TypeError(f"Cannot deserialize into {message_type.__name__!r}")
