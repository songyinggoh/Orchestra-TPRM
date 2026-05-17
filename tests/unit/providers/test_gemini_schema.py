"""P-4: pydantic_to_gemini_schema strips JSON-Schema-Draft features Gemini
rejects (additionalProperties, $defs, $ref, title, description) and maps
anyOf:[X,null] -> nullable: true."""
from __future__ import annotations

from typing import Literal

import pytest
from pydantic import BaseModel

from orchestra.providers._gemini_schema import (
    GeminiSchemaError,
    pydantic_to_gemini_schema,
)


class Citation(BaseModel):
    file_id: str
    page: int | None = None
    snippet: str


class Finding(BaseModel):
    agent: str
    category: str
    severity: Literal["low", "medium", "high", "critical"]
    summary: str
    evidence: list[Citation] = []


def test_strips_unsupported_keys():
    schema = pydantic_to_gemini_schema(Finding)
    flat = repr(schema)
    for banned in ("additionalProperties", "$defs", "$ref", "title", "description"):
        assert banned not in flat, f"{banned} should be stripped"


def test_anyOf_with_null_becomes_nullable():
    schema = pydantic_to_gemini_schema(Citation)
    page = schema["properties"]["page"]
    assert page.get("nullable") is True
    assert page.get("type") == "integer"
    assert "anyOf" not in page


def test_inlines_refs_into_array_items():
    schema = pydantic_to_gemini_schema(Finding)
    items = schema["properties"]["evidence"]["items"]
    # Items must be inlined Citation, not a $ref
    assert items["type"] == "object"
    assert "file_id" in items["properties"]


def test_literal_becomes_string_with_enum():
    schema = pydantic_to_gemini_schema(Finding)
    sev = schema["properties"]["severity"]
    assert sev["type"] == "string"
    assert sorted(sev["enum"]) == ["critical", "high", "low", "medium"]


def test_unknown_construct_raises_clear_error():
    class Weird(BaseModel):
        # Tuples are not in Gemini's responseSchema subset
        pair: tuple[int, str]

    with pytest.raises(GeminiSchemaError):
        pydantic_to_gemini_schema(Weird)
