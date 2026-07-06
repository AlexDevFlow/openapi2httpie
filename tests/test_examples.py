from openapi2httpie.examples import ExampleBuilder
from openapi2httpie.resolver import Resolver


def build(schema, root=None, **kw):
    root = root or {}
    return ExampleBuilder(Resolver(root), **kw).build(schema)


def test_prefers_explicit_example():
    assert build({"type": "string", "example": "hi"}) == "hi"


def test_default_and_enum_and_const():
    assert build({"type": "string", "default": "d"}) == "d"
    assert build({"type": "string", "enum": ["a", "b"]}) == "a"
    assert build({"const": 7}) == 7


def test_format_aware_strings():
    assert build({"type": "string", "format": "email"}) == "user@example.com"
    assert build({"type": "string", "format": "date"}) == "2024-01-01"
    assert build({"type": "string", "format": "uuid"}).count("-") == 4


def test_scalars():
    assert build({"type": "integer"}) == 0
    assert build({"type": "integer", "minimum": 5}) == 5
    assert build({"type": "boolean"}) is True
    assert build({"type": "string"}) == "string"


def test_object_required_only_by_default():
    schema = {
        "type": "object",
        "required": ["a"],
        "properties": {"a": {"type": "string"}, "b": {"type": "integer"}},
    }
    assert build(schema) == {"a": "string"}


def test_object_include_optional():
    schema = {
        "type": "object",
        "required": ["a"],
        "properties": {"a": {"type": "string"}, "b": {"type": "integer"}},
    }
    out = ExampleBuilder(Resolver({}), include_optional=True).build(schema)
    assert out == {"a": "string", "b": 0}


def test_object_without_required_includes_all():
    schema = {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "integer"}}}
    assert build(schema) == {"a": "string", "b": 0}


def test_array():
    assert build({"type": "array", "items": {"type": "integer"}}) == [0]


def test_all_of_merges_objects():
    root = {
        "components": {
            "schemas": {
                "Base": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
            }
        }
    }
    schema = {
        "allOf": [
            {"$ref": "#/components/schemas/Base"},
            {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        ]
    }
    assert build(schema, root) == {"id": 0, "name": "string"}


def test_one_of_takes_first():
    schema = {"oneOf": [{"type": "string"}, {"type": "integer"}]}
    assert build(schema) == "string"


def test_ref_resolution():
    root = {"components": {"schemas": {"S": {"type": "string", "example": "ok"}}}}
    assert build({"$ref": "#/components/schemas/S"}, root) == "ok"


def test_recursive_schema_terminates():
    root = {
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "required": ["child"],
                    "properties": {"child": {"$ref": "#/components/schemas/Node"}},
                }
            }
        }
    }
    # Must not hang or overflow; recursion breaks at the repeated ref.
    out = build({"$ref": "#/components/schemas/Node"}, root)
    assert isinstance(out, dict)


def test_nullable_union_type_31():
    assert build({"type": ["string", "null"]}) == "string"
