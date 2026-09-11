import json

import pytest
from pydantic import BaseModel

from rmf2_vda5050_master.model_utils import PyModel, _inline_refs


# --- _inline_refs unit tests ---

def test_inline_refs_no_refs():
    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    assert _inline_refs(schema) == schema


def test_inline_refs_no_definitions():
    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    result = _inline_refs(schema)
    assert result == schema
    assert "definitions" not in result
    assert "$defs" not in result


def test_inline_refs_definitions_inlined():
    schema = {
        "type": "object",
        "definitions": {
            "item": {"type": "string", "description": "an item"}
        },
        "properties": {
            "value": {"$ref": "#/definitions/item"}
        },
    }
    result = _inline_refs(schema)
    assert result["properties"]["value"] == {"type": "string", "description": "an item"}
    assert "definitions" not in result


def test_inline_refs_defs_inlined():
    schema = {
        "type": "object",
        "$defs": {
            "item": {"type": "integer"}
        },
        "properties": {
            "count": {"$ref": "#/$defs/item"}
        },
    }
    result = _inline_refs(schema)
    assert result["properties"]["count"] == {"type": "integer"}
    assert "$defs" not in result


def test_inline_refs_nested():
    schema = {
        "type": "object",
        "definitions": {
            "inner": {"type": "object", "properties": {"x": {"type": "number"}}}
        },
        "properties": {
            "outer": {
                "type": "array",
                "items": {"$ref": "#/definitions/inner"}
            }
        },
    }
    result = _inline_refs(schema)
    assert result["properties"]["outer"]["items"] == {
        "type": "object",
        "properties": {"x": {"type": "number"}},
    }
    assert "definitions" not in result


def test_inline_refs_unknown_ref_preserved():
    schema = {
        "type": "object",
        "definitions": {"item": {"type": "string"}},
        "properties": {
            "a": {"$ref": "#/definitions/item"},
            "b": {"$ref": "#/definitions/missing"},
        },
    }
    result = _inline_refs(schema)
    assert result["properties"]["a"] == {"type": "string"}
    # unknown ref is left as-is
    assert result["properties"]["b"] == {"$ref": "#/definitions/missing"}


# --- Integration: PyModel[Order] schema generation doesn't crash ---

def test_pymodel_order_schema_no_ref_error():
    import rmf2_vda5050_master.models  # triggers PyModel.register for Order  # noqa: F401
    from vda5050_core.types import Order

    class Wrapper(BaseModel):
        order: PyModel[Order] | None = None

    # This raised KeyError before _inline_refs was added
    schema = Wrapper.model_json_schema()
    assert "order" in schema["properties"]
    # No unresolved $ref entries pointing to #/definitions/ remain
    text = json.dumps(schema)
    assert "#/definitions/" not in text
