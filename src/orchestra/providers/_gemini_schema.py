"""Convert Pydantic JSON Schema (Draft 2020-12) to Gemini responseSchema (OpenAPI 3.0 subset).

Gemini's responseSchema accepts a strict subset:
  - type: string, integer, number, boolean, array, object
  - format (limited), enum, properties, required, items, nullable
Not accepted: $defs, $ref, additionalProperties, title, description, anyOf,
oneOf, allOf, const, pattern, minLength, etc.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

_BANNED_KEYS = {
    "additionalProperties",
    "$defs",
    "$ref",
    "title",
    "description",
    "default",
}


class GeminiSchemaError(ValueError):
    """Raised when a Pydantic schema can't be expressed in Gemini's subset."""


def pydantic_to_gemini_schema(model: type[BaseModel]) -> dict[str, Any]:
    raw = model.model_json_schema()
    defs = raw.get("$defs", {})
    return _convert(raw, defs)


def _convert(node: Any, defs: dict[str, Any]) -> Any:
    if not isinstance(node, dict):
        return node

    # Resolve $ref against $defs (inline)
    if "$ref" in node:
        ref = node["$ref"]
        if not ref.startswith("#/$defs/"):
            raise GeminiSchemaError(f"unsupported $ref: {ref}")
        target = defs.get(ref.removeprefix("#/$defs/"))
        if target is None:
            raise GeminiSchemaError(f"dangling $ref: {ref}")
        return _convert(target, defs)

    # Map anyOf:[X, null] -> nullable
    if "anyOf" in node:
        variants = node["anyOf"]
        non_null = [v for v in variants if v.get("type") != "null"]
        if len(variants) == 2 and len(non_null) == 1:
            converted = _convert(non_null[0], defs)
            converted["nullable"] = True
            for k, v in node.items():
                if k != "anyOf":
                    converted.setdefault(k, v)
            return _strip(converted)
        raise GeminiSchemaError(f"unsupported anyOf shape: {variants}")

    # Recurse into properties / items
    out: dict[str, Any] = {}
    for k, v in node.items():
        if k in _BANNED_KEYS:
            continue
        if k == "properties" and isinstance(v, dict):
            out["properties"] = {pk: _convert(pv, defs) for pk, pv in v.items()}
        elif k == "items":
            out["items"] = _convert(v, defs)
        else:
            out[k] = v

    # Gemini does not support tuple types (prefixItems). Convert to a flat array
    # using the shared item type.  Validate that all prefix items are homogeneous
    # (same JSON-schema type) before proceeding — heterogeneous tuples cannot be
    # expressed in Gemini's schema subset.
    if "prefixItems" in out or "prefixItems" in node:
        prefix = node.get("prefixItems", [])
        if len(prefix) < 2:
            raise GeminiSchemaError(
                f"prefixItems tuple must have at least 2 elements, got {prefix!r}"
            )
        types = {p.get("type") for p in prefix if isinstance(p, dict)}
        if len(types) > 1:
            raise GeminiSchemaError(
                f"Heterogeneous prefixItems tuple cannot be expressed in Gemini schema: {prefix!r}"
            )
        item_schema: dict[str, Any] = _convert(prefix[0], defs) if prefix else {}
        out.pop("prefixItems", None)
        out["type"] = "array"
        if item_schema:
            out["items"] = item_schema

    return out


def _strip(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if k not in _BANNED_KEYS}
