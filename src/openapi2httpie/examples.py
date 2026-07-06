"""Synthesize example values from JSON Schema fragments.

The goal is a *useful, runnable* example, not a validator. We prefer values the
spec author actually provided (``example``/``examples``/``default``/``enum``)
and fall back to type/format-aware placeholders. Recursion is bounded by depth
and by a set of already-expanded ``$ref``s so recursive schemas terminate.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .resolver import Resolver

# Realistic placeholders keyed by JSON Schema ``format``.
_FORMAT_EXAMPLES: Dict[str, Any] = {
    "date-time": "2024-01-01T00:00:00Z",
    "date": "2024-01-01",
    "time": "12:00:00",
    "duration": "P1D",
    "email": "user@example.com",
    "idn-email": "user@example.com",
    "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "uri": "https://example.com",
    "uri-reference": "/example",
    "url": "https://example.com",
    "hostname": "example.com",
    "ipv4": "192.0.2.1",
    "ipv6": "2001:db8::1",
    "byte": "U3dhZ2dlciByb2Nrcw==",
    "binary": "binary data",
    "password": "s3cr3t",
}


class ExampleBuilder:
    """Builds example values for schemas resolved against a :class:`Resolver`."""

    def __init__(
        self,
        resolver: Resolver,
        include_optional: bool = False,
        max_depth: int = 12,
    ) -> None:
        self.resolver = resolver
        self.include_optional = include_optional
        self.max_depth = max_depth

    # -- public ------------------------------------------------------------

    def build(self, schema: Any, depth: int = 0, seen: Tuple[str, ...] = ()) -> Any:
        """Return an example value for ``schema``."""
        if not isinstance(schema, dict):
            return None

        if "$ref" in schema:
            resolved, seen2 = self._deref(schema, seen)
            if resolved is None:  # cycle or too deep
                return None
            return self.build(resolved, depth, seen2)

        # Author-provided values win.
        explicit = self._explicit_value(schema)
        if explicit is not _UNSET:
            return explicit

        if "allOf" in schema:
            return self._all_of(schema, depth, seen)
        for combiner in ("oneOf", "anyOf"):
            options = schema.get(combiner)
            if isinstance(options, list) and options:
                return self.build(options[0], depth, seen)

        return self._by_type(schema, depth, seen)

    # -- internals ---------------------------------------------------------

    def _deref(self, node: Any, seen: Tuple[str, ...]) -> Tuple[Optional[Any], Tuple[str, ...]]:
        """Follow a single ``$ref`` (cycle-safe). Returns ``(node|None, seen)``."""
        while isinstance(node, dict) and "$ref" in node:
            ref = node["$ref"]
            if ref in seen:
                return None, seen
            seen = seen + (ref,)
            try:
                node = self.resolver.lookup(ref)
            except Exception:
                return None, seen
        return node, seen

    def _explicit_value(self, schema: Dict[str, Any]) -> Any:
        if "example" in schema:
            return schema["example"]
        if "examples" in schema:
            ex = schema["examples"]
            if isinstance(ex, list) and ex:
                return ex[0]
            if isinstance(ex, dict) and ex:
                first = next(iter(ex.values()))
                if isinstance(first, dict) and "value" in first:
                    return first["value"]
                return first
        if "default" in schema:
            return schema["default"]
        if "const" in schema:
            return schema["const"]
        enum = schema.get("enum")
        if isinstance(enum, list) and enum:
            return enum[0]
        return _UNSET

    def _all_of(self, schema: Dict[str, Any], depth: int, seen: Tuple[str, ...]) -> Any:
        merged_props: Dict[str, Any] = dict(schema.get("properties", {}))
        merged_required = list(schema.get("required", []))
        non_object: Any = _UNSET
        for sub in schema.get("allOf", []):
            resolved, seen2 = self._deref(sub, seen)
            if not isinstance(resolved, dict):
                continue
            if "properties" in resolved or resolved.get("type") == "object":
                merged_props.update(resolved.get("properties", {}))
                merged_required.extend(resolved.get("required", []))
            else:
                non_object = self.build(resolved, depth + 1, seen2)
        if merged_props:
            synthetic = {
                "type": "object",
                "properties": merged_props,
                "required": merged_required,
            }
            return self._object(synthetic, depth, seen)
        return None if non_object is _UNSET else non_object

    def _by_type(self, schema: Dict[str, Any], depth: int, seen: Tuple[str, ...]) -> Any:
        t = schema.get("type")
        if isinstance(t, list):  # OpenAPI 3.1 union types, e.g. ["string", "null"]
            t = next((x for x in t if x != "null"), t[0] if t else None)

        if t == "object" or (t is None and ("properties" in schema or "additionalProperties" in schema)):
            return self._object(schema, depth, seen)
        if t == "array":
            return self._array(schema, depth, seen)
        if t == "string":
            return self._string(schema)
        if t == "integer":
            return int(schema.get("minimum", 0))
        if t == "number":
            return schema.get("minimum", 0)
        if t == "boolean":
            return True
        if t == "null":
            return None
        if "properties" in schema:
            return self._object(schema, depth, seen)
        return "string"

    def _object(self, schema: Dict[str, Any], depth: int, seen: Tuple[str, ...]) -> Dict[str, Any]:
        if depth >= self.max_depth:
            return {}
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        result: Dict[str, Any] = {}
        for name, subschema in props.items():
            # Skip optional properties unless asked, but only when the schema
            # actually declares a required set; otherwise include everything.
            if required and not self.include_optional and name not in required:
                continue
            result[name] = self.build(subschema, depth + 1, seen)
        return result

    def _array(self, schema: Dict[str, Any], depth: int, seen: Tuple[str, ...]) -> Any:
        if depth >= self.max_depth:
            return []
        prefix = schema.get("prefixItems")
        if isinstance(prefix, list) and prefix:
            return [self.build(item, depth + 1, seen) for item in prefix]
        items = schema.get("items")
        if not items:
            return []
        return [self.build(items, depth + 1, seen)]

    def _string(self, schema: Dict[str, Any]) -> str:
        fmt = schema.get("format")
        if fmt in _FORMAT_EXAMPLES:
            return _FORMAT_EXAMPLES[fmt]
        min_len = schema.get("minLength")
        value = "string"
        if isinstance(min_len, int) and min_len > len(value):
            value = value + "x" * (min_len - len(value))
        return value


class _Unset:
    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "<UNSET>"


_UNSET = _Unset()
