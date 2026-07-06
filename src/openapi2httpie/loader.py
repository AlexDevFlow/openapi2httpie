"""Load an OpenAPI/Swagger document from a file, stdin, or URL and detect its
dialect. Parsing is done with :func:`yaml.safe_load`, which also accepts JSON
(JSON is a subset of YAML)."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Dict, Tuple
from urllib.request import urlopen

import yaml

from .errors import SpecLoadError, SpecValidationError


class _SpecYamlLoader(yaml.SafeLoader):
    """SafeLoader that leaves date/time scalars as strings.

    YAML 1.1 resolves bare values like ``2020-01-01`` to ``datetime.date``,
    which are not JSON-serialisable and are never what an OpenAPI author means
    (the spec is JSON-shaped). Dropping the timestamp resolver keeps them as the
    strings they were written as.
    """


_SpecYamlLoader.yaml_implicit_resolvers = {
    key: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}

# Spec dialects we normalise.
SWAGGER_2 = "swagger2"
OPENAPI_3 = "openapi3"


@dataclass
class LoadedSpec:
    doc: Dict[str, Any]
    dialect: str  # SWAGGER_2 | OPENAPI_3
    version: str  # the raw version string, e.g. "3.0.1" or "2.0"
    source: str   # where it came from, for error messages


def _read_source(src: str) -> str:
    """Return raw text for ``src`` which may be ``-`` (stdin), a URL or a path."""
    if src == "-":
        return sys.stdin.read()
    if src.startswith(("http://", "https://")):
        try:
            with urlopen(src, timeout=30) as resp:  # noqa: S310 - user supplied
                return resp.read().decode("utf-8")
        except Exception as exc:  # pragma: no cover - network
            raise SpecLoadError(f"could not fetch spec from {src}: {exc}") from exc
    try:
        with open(src, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise SpecLoadError(f"could not read spec file {src!r}: {exc}") from exc


def parse_text(text: str, source: str = "<string>") -> Dict[str, Any]:
    """Parse spec ``text`` (JSON or YAML) into a dict."""
    # Try JSON first for a precise error and speed, then fall back to YAML.
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            data = yaml.load(text, Loader=_SpecYamlLoader)
        except yaml.YAMLError as exc:
            raise SpecLoadError(f"{source}: not valid JSON or YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SpecValidationError(
            f"{source}: top-level document must be a mapping, got {type(data).__name__}"
        )
    return data


def detect_dialect(doc: Dict[str, Any]) -> Tuple[str, str]:
    """Return ``(dialect, version_string)`` for a parsed document."""
    if "openapi" in doc:
        version = str(doc["openapi"])
        if not version.startswith("3"):
            raise SpecValidationError(
                f"unsupported OpenAPI version {version!r}; only 3.x is supported"
            )
        return OPENAPI_3, version
    if "swagger" in doc:
        version = str(doc["swagger"])
        if not version.startswith("2"):
            raise SpecValidationError(
                f"unsupported Swagger version {version!r}; only 2.0 is supported"
            )
        return SWAGGER_2, version
    raise SpecValidationError(
        "document has neither an 'openapi' nor a 'swagger' version key; "
        "this does not look like an OpenAPI/Swagger spec"
    )


def validate_minimal(doc: Dict[str, Any], source: str) -> None:
    """Cheap structural sanity checks so we fail early with a clear message."""
    paths = doc.get("paths")
    if paths is None:
        raise SpecValidationError(f"{source}: spec has no 'paths' object")
    if not isinstance(paths, dict):
        raise SpecValidationError(f"{source}: 'paths' must be a mapping")


def load(src: str) -> LoadedSpec:
    """Load, parse, detect and lightly validate a spec from ``src``."""
    text = _read_source(src)
    doc = parse_text(text, src)
    dialect, version = detect_dialect(doc)
    validate_minimal(doc, src)
    return LoadedSpec(doc=doc, dialect=dialect, version=version, source=src)
