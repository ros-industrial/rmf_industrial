"""PyModel: generic annotated bridge between vda5050_core pybind11 types and FastAPI."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Annotated, Any, ClassVar, Generic, TypeVar

from fastapi import Body
from pydantic import BaseModel, GetPydanticSchema, model_validator
from pydantic_core import core_schema
from typing_extensions import Self

_LOG = logging.getLogger(__name__)

T = TypeVar("T")

_JsonSchema = dict[str, Any]


_BASIC_TYPES = (str, int, float, bool, list, dict, type(None))


def _inline_refs(schema: _JsonSchema) -> _JsonSchema:
    """Inline local ``$ref`` entries so the schema is self-contained.

    Pydantic 2's ``GetPydanticSchema`` does not hoist nested ``$defs`` — any ``$ref``
    it didn't register itself causes a ``KeyError`` during JSON schema generation.
    """
    defs = {**schema.get("definitions", {}), **schema.get("$defs", {})}
    if not defs or '"$ref"' not in json.dumps(schema):
        return schema

    _LOG.warning(
        "Schema '%s' contains local $ref entries; inlining definitions for OpenAPI compatibility.",
        schema.get("title", "<unknown>"),
    )

    def _resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node and len(node) == 1:
                for prefix in ("#/definitions/", "#/$defs/"):
                    if node["$ref"].startswith(prefix):
                        key = node["$ref"][len(prefix):]
                        if key in defs:
                            return _resolve(defs[key])
            return {k: _resolve(v) for k, v in node.items() if k not in ("definitions", "$defs")}
        if isinstance(node, list):
            return [_resolve(item) for item in node]
        return node

    return _resolve(schema)


def _coerce_pybind_value(v: Any) -> Any:
    """Convert pybind11 enums (and similar) to their .name string."""
    if isinstance(v, _BASIC_TYPES):
        return v
    if hasattr(v, "name"):
        return v.name
    return v


class FromVda5050(BaseModel):
    """Base class that auto-maps pybind11 vda5050 objects to Pydantic models via model_fields.

    TODO: replace field-by-field getattr mapping with native C++ JSON serialization
    (obj.json()) and validate against the vda5050 JSON schema, consistent with how
    PyModel handles State/Connection/InstantActions.
    """

    @model_validator(mode="before")
    @classmethod
    def _coerce_from_pybind(cls, data: Any) -> Any:
        if not isinstance(data, (dict, BaseModel)):
            return {
                field: _coerce_pybind_value(getattr(data, field))
                for field in cls.model_fields
                if hasattr(data, field)
            }
        return data

    @classmethod
    def from_vda5050(cls, obj: Any) -> Self:
        return cls.model_validate(obj)


def _make_vda_schema(vda_type: type, json_schema: _JsonSchema | None = None):
    _schema = json_schema

    def validate(value: Any) -> Any:
        if isinstance(value, dict):
            return vda_type.from_json(value)
        return value

    def serialize(value: Any) -> dict | None:
        return None if value is None else value.json()

    def get_core_schema(tp, handler):
        return core_schema.no_info_plain_validator_function(
            validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                serialize,
                return_schema=core_schema.nullable_schema(core_schema.dict_schema()),
            ),
        )

    def get_json_schema(cs, handler) -> _JsonSchema:
        return _schema if _schema is not None else {"type": "object", "title": vda_type.__name__}

    return get_core_schema, get_json_schema


class PyModel(Generic[T]):
    """Annotated bridge for vda5050_core pybind11 types.

    - Input (request body): accepts a dict and calls T.from_json(data)
    - Output (response): calls .json() on the pybind11 object

    Register a JSON schema file for a type so FastAPI can generate accurate docs::

        PyModel.register(State, "schemas/state.json")

    Usage::

        @app.post("/foo")
        def handler(body: PyModel[InstantActions]) -> PyModel[State]:
            ...
    """

    _registry: ClassVar[dict[type, _JsonSchema]] = {}

    @classmethod
    def register(
        cls,
        vda_type: type,
        schema_path: str | Path,
        property_path: str | None = None,
    ) -> None:
        text = Path(schema_path).read_text()
        text = re.sub(r",\s*([}\]])", r"\1", text)  # strip trailing commas (JSON5)
        schema = json.loads(text)
        if property_path is not None:
            for key in property_path.split("."):
                schema = schema[key]
        cls._registry[vda_type] = _inline_refs(schema)

    def __class_getitem__(cls, vda_type: type) -> type:
        get_core_schema, get_json_schema = _make_vda_schema(
            vda_type, cls._registry.get(vda_type)
        )
        return Annotated[
            vda_type, GetPydanticSchema(get_core_schema, get_json_schema), Body()
        ]
