"""Exception types raised by openapi2httpie."""

from __future__ import annotations


class OpenAPI2HTTPieError(Exception):
    """Base class for all errors raised by this package."""


class SpecLoadError(OpenAPI2HTTPieError):
    """The spec file could not be read or parsed."""


class SpecValidationError(OpenAPI2HTTPieError):
    """The document parsed but is not a usable OpenAPI/Swagger spec."""


class RefResolutionError(OpenAPI2HTTPieError):
    """A ``$ref`` pointer could not be resolved."""
