import pytest

from openapi2httpie.errors import SpecLoadError, SpecValidationError
from openapi2httpie.loader import OPENAPI_3, SWAGGER_2, detect_dialect, parse_text, validate_minimal


def test_parse_json():
    doc = parse_text('{"openapi": "3.0.0", "paths": {}}')
    assert doc["openapi"] == "3.0.0"


def test_parse_yaml():
    doc = parse_text("openapi: 3.0.0\npaths: {}\n")
    assert doc["openapi"] == "3.0.0"


def test_parse_garbage_raises():
    with pytest.raises(SpecLoadError):
        parse_text("this: is: not: valid: yaml: [")


def test_parse_non_mapping_raises():
    with pytest.raises(SpecValidationError):
        parse_text("- just\n- a\n- list\n")


def test_detect_openapi3():
    assert detect_dialect({"openapi": "3.1.0"}) == (OPENAPI_3, "3.1.0")


def test_detect_swagger2():
    assert detect_dialect({"swagger": "2.0"}) == (SWAGGER_2, "2.0")


def test_detect_unsupported_openapi_version():
    with pytest.raises(SpecValidationError):
        detect_dialect({"openapi": "2.0"})


def test_detect_unsupported_swagger_version():
    with pytest.raises(SpecValidationError):
        detect_dialect({"swagger": "1.2"})


def test_detect_missing_version_key():
    with pytest.raises(SpecValidationError):
        detect_dialect({"paths": {}})


def test_validate_minimal_requires_paths():
    with pytest.raises(SpecValidationError):
        validate_minimal({"openapi": "3.0.0"}, "x")
    validate_minimal({"paths": {}}, "x")  # no raise
