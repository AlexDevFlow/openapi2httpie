import pytest

from openapi2httpie.errors import RefResolutionError
from openapi2httpie.resolver import Resolver


def _doc():
    return {
        "components": {
            "schemas": {
                "Pet": {"type": "object", "properties": {"name": {"type": "string"}}},
                "Alias": {"$ref": "#/components/schemas/Pet"},
                "Node": {
                    "type": "object",
                    "properties": {"child": {"$ref": "#/components/schemas/Node"}},
                },
            }
        },
        "weird": {"m/n": 42, "x~y": 43},
    }


def test_lookup_simple():
    r = Resolver(_doc())
    node = r.lookup("#/components/schemas/Pet")
    assert node["type"] == "object"


def test_lookup_escaped_tokens():
    # RFC 6901: "/" encodes as ~1, "~" encodes as ~0
    r = Resolver(_doc())
    assert r.lookup("#/weird/m~1n") == 42
    assert r.lookup("#/weird/x~0y") == 43


def test_lookup_root():
    r = Resolver(_doc())
    assert r.lookup("#") is r.root


def test_lookup_missing_raises():
    r = Resolver(_doc())
    with pytest.raises(RefResolutionError):
        r.lookup("#/components/schemas/DoesNotExist")


def test_non_local_ref_raises():
    r = Resolver(_doc())
    with pytest.raises(RefResolutionError):
        r.lookup("https://example.com/x.json#/Foo")


def test_deref_follows_chain():
    r = Resolver(_doc())
    node = r.deref({"$ref": "#/components/schemas/Alias"})
    assert node["properties"]["name"]["type"] == "string"


def test_deref_detects_cycle():
    doc = {"a": {}, "b": {}}
    doc["a"] = {"$ref": "#/b"}
    doc["b"] = {"$ref": "#/a"}
    r = Resolver(doc)
    with pytest.raises(RefResolutionError):
        r.deref({"$ref": "#/a"})


def test_deref_non_ref_returns_input():
    r = Resolver(_doc())
    node = {"type": "string"}
    assert r.deref(node) is node
