"""Resolve local ``$ref`` JSON pointers within a spec document.

Only local references (``#/...``) are resolved. Remote/URL references are rare
in practice and unsupported; encountering one raises :class:`RefResolutionError`
so the caller can warn rather than silently produce wrong output.
"""

from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import unquote

from .errors import RefResolutionError


def _unescape_token(token: str) -> str:
    """Decode a JSON-Pointer token (RFC 6901 + percent-encoding)."""
    return unquote(token).replace("~1", "/").replace("~0", "~")


class Resolver:
    """Navigates ``$ref`` pointers against a root document."""

    def __init__(self, root: Dict[str, Any]) -> None:
        self.root = root

    def lookup(self, ref: str) -> Any:
        """Return the node a ``$ref`` string points at (not deep-resolved)."""
        if not ref.startswith("#/") and ref != "#":
            raise RefResolutionError(
                f"unsupported non-local $ref {ref!r}; only local '#/...' refs are supported"
            )
        node: Any = self.root
        if ref == "#":
            return node
        for token in ref[2:].split("/"):
            key = _unescape_token(token)
            if isinstance(node, dict):
                if key not in node:
                    raise RefResolutionError(f"$ref {ref!r} not found (missing {key!r})")
                node = node[key]
            elif isinstance(node, list):
                try:
                    node = node[int(key)]
                except (ValueError, IndexError) as exc:
                    raise RefResolutionError(f"$ref {ref!r} bad list index {key!r}") from exc
            else:
                raise RefResolutionError(f"$ref {ref!r} traverses into a scalar")
        return node

    def deref(self, node: Any, _seen: List[str] | None = None) -> Any:
        """Follow a chain of ``$ref``s a single logical level.

        Given a node that may be ``{"$ref": ...}``, return the referenced node,
        following chained refs. Guards against ref cycles.
        """
        seen = _seen if _seen is not None else []
        while isinstance(node, dict) and "$ref" in node and len(node) == 1:
            ref = node["$ref"]
            if ref in seen:
                raise RefResolutionError(f"circular $ref chain: {' -> '.join(seen + [ref])}")
            seen.append(ref)
            node = self.lookup(ref)
        return node
