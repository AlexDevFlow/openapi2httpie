"""Intermediate representation (IR) shared by every emitter.

The extractor normalises both Swagger 2.0 and OpenAPI 3.x documents into these
dataclasses, so emitters never have to care which spec dialect they came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional


# ---- Security -------------------------------------------------------------

@dataclass
class SecurityScheme:
    """A normalised authentication scheme.

    ``kind`` is one of: ``basic``, ``bearer``, ``apiKey``, ``oauth2``,
    ``openIdConnect``. For ``apiKey`` the credential travels in ``location``
    (``header`` / ``query`` / ``cookie``) under ``param_name``.
    """

    name: str  # the scheme's key in the spec (e.g. "ApiKeyAuth")
    kind: str
    location: Optional[str] = None      # apiKey only: header|query|cookie
    param_name: Optional[str] = None    # apiKey only: the header/query/cookie name
    bearer_format: Optional[str] = None  # informational (e.g. "JWT")
    description: str = ""


# ---- Request pieces -------------------------------------------------------

@dataclass
class Param:
    """A path, query or header parameter with a synthesised example value."""

    name: str
    location: str  # path | query | header
    value: Any     # example value (may be None if unknown)
    required: bool = False
    description: str = ""
    explode: bool = True
    style: Optional[str] = None


@dataclass
class Body:
    """A request body.

    ``kind`` is one of:

    * ``none``      – no body
    * ``json``      – ``value`` holds a JSON-serialisable structure
    * ``form``      – ``value`` is a flat ``dict`` (x-www-form-urlencoded)
    * ``multipart`` – ``value`` is a flat ``dict``; ``file_fields`` names the
      properties that are file uploads
    * ``raw``       – ``raw`` holds a raw text body of ``content_type``
    """

    kind: str = "none"
    value: Any = None
    raw: Optional[str] = None
    content_type: Optional[str] = None
    file_fields: List[str] = field(default_factory=list)


@dataclass
class Request:
    """A single API operation, fully resolved and ready to emit."""

    method: str            # upper-case HTTP verb
    path: str              # templated path, e.g. "/users/{id}"
    server_url: str        # base URL (may still contain {vars})
    operation_id: str = ""
    summary: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    path_params: List[Param] = field(default_factory=list)
    query_params: List[Param] = field(default_factory=list)
    header_params: List[Param] = field(default_factory=list)
    body: Body = field(default_factory=Body)
    # Applicable security schemes. Semantics are OR across the outer list; we
    # only ever emit the first requirement, but keep the rest for reference.
    security: List[List[SecurityScheme]] = field(default_factory=list)
    deprecated: bool = False

    @property
    def label(self) -> str:
        """A stable human label for comments / Postman item names."""
        if self.operation_id:
            return self.operation_id
        if self.summary:
            return self.summary
        return f"{self.method} {self.path}"


@dataclass
class ApiModel:
    """The whole API, normalised."""

    title: str = "API"
    version: str = ""
    description: str = ""
    servers: List[str] = field(default_factory=list)
    requests: List[Request] = field(default_factory=list)

    @property
    def primary_server(self) -> str:
        return self.servers[0] if self.servers else ""
