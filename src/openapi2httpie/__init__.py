"""openapi2httpie — turn an OpenAPI/Swagger spec into runnable HTTPie commands
or a Postman collection you can import into HTTPie Desktop."""

from __future__ import annotations

from typing import List, Optional

from .emitters.httpie import HttpieEmitter, HttpieOptions
from .emitters.postman import PostmanEmitter
from .extract import extract
from .loader import load
from .model import ApiModel, Request

__all__ = [
    "__version__",
    "ApiModel",
    "Request",
    "HttpieEmitter",
    "HttpieOptions",
    "PostmanEmitter",
    "load",
    "extract",
    "build_model",
    "to_httpie",
    "to_postman",
]

__version__ = "0.1.0"


def build_model(src: str, include_optional: bool = False) -> ApiModel:
    """Load ``src`` and return the normalised :class:`ApiModel`."""
    return extract(load(src), include_optional=include_optional)


def to_httpie(src: str, options: Optional[HttpieOptions] = None, include_optional: bool = False) -> str:
    """Convenience: spec source → HTTPie shell script."""
    model = build_model(src, include_optional=include_optional)
    return HttpieEmitter(options).render_script(model)


def to_postman(src: str, base_url: Optional[str] = None, include_optional: bool = False) -> str:
    """Convenience: spec source → Postman v2.1 collection JSON."""
    model = build_model(src, include_optional=include_optional)
    return PostmanEmitter(base_url=base_url).render(model)
