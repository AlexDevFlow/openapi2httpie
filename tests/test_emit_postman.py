import json

from openapi2httpie.emitters.postman import PostmanEmitter
from openapi2httpie.extract import extract
from openapi2httpie.loader import OPENAPI_3, LoadedSpec


def collection(doc, **kw):
    model = extract(LoadedSpec(doc=doc, dialect=OPENAPI_3, version="3.0.3", source="t"))
    return PostmanEmitter(**kw).build(model)


def _all_requests(items):
    """Flatten folders to (name, request) pairs."""
    out = []
    for it in items:
        if "item" in it:
            out.extend(_all_requests(it["item"]))
        elif "request" in it:
            out.append((it["name"], it["request"]))
    return out


def test_schema_and_valid_json():
    doc = {"openapi": "3.0.0", "info": {"title": "X"}, "paths": {"/p": {"get": {}}}}
    col = collection(doc)
    # Round-trips through json cleanly.
    assert json.loads(json.dumps(col))
    assert col["info"]["schema"].endswith("v2.1.0/collection.json")


def test_deterministic_id():
    doc = {"openapi": "3.0.0", "info": {"title": "X", "version": "1"}, "paths": {"/p": {"get": {}}}}
    assert collection(doc)["info"]["_postman_id"] == collection(doc)["info"]["_postman_id"]


def test_tag_folders():
    doc = {
        "openapi": "3.0.0",
        "paths": {
            "/a": {"get": {"tags": ["Pets"], "operationId": "listPets"}},
            "/b": {"get": {"operationId": "noTag"}},
        },
    }
    items = collection(doc)["item"]
    folders = [it for it in items if "item" in it]
    assert any(f["name"] == "Pets" for f in folders)


def test_structured_url_with_variable_and_query():
    doc = {
        "openapi": "3.0.0",
        "paths": {
            "/users/{id}": {
                "get": {
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}},
                        {"name": "q", "in": "query", "schema": {"type": "string"}},
                    ]
                }
            }
        },
    }
    _, req = _all_requests(collection(doc)["item"])[0]
    url = req["url"]
    assert url["path"] == ["users", ":id"]
    assert url["variable"][0]["key"] == "id"
    assert url["query"][0]["key"] == "q"
    assert url["raw"].startswith("{{baseUrl}}/users/:id?q=")


def test_native_auth_objects():
    doc = {
        "openapi": "3.0.0",
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"},
                "apiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
            }
        },
        "paths": {
            "/b": {"get": {"security": [{"bearerAuth": []}]}},
            "/k": {"get": {"security": [{"apiKeyAuth": []}]}},
        },
    }
    reqs = {name: r for name, r in _all_requests(collection(doc)["item"])}
    bearer = [r for r in reqs.values() if r["url"]["raw"].endswith("/b")][0]
    apikey = [r for r in reqs.values() if r["url"]["raw"].endswith("/k")][0]
    assert bearer["auth"]["type"] == "bearer"
    assert apikey["auth"]["type"] == "apikey"
    incol = {v["key"]: v["value"] for v in apikey["auth"]["apikey"]}
    assert incol["key"] == "X-API-Key" and incol["in"] == "header"


def test_json_body_raw_mode():
    doc = {
        "openapi": "3.0.0",
        "paths": {
            "/u": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["name"],
                                    "properties": {"name": {"type": "string"}},
                                }
                            }
                        }
                    }
                }
            }
        },
    }
    _, req = _all_requests(collection(doc)["item"])[0]
    assert req["body"]["mode"] == "raw"
    assert req["body"]["options"]["raw"]["language"] == "json"
    assert json.loads(req["body"]["raw"]) == {"name": "string"}


def test_base_url_variable_and_override():
    doc = {"openapi": "3.0.0", "servers": [{"url": "https://spec.example"}], "paths": {"/p": {"get": {}}}}
    col = collection(doc, base_url="https://override.example")
    variables = {v["key"]: v["value"] for v in col["variable"]}
    assert variables["baseUrl"] == "https://override.example"
