from openapi2httpie.extract import extract
from openapi2httpie.loader import OPENAPI_3, SWAGGER_2, LoadedSpec


def oas3(doc, **kw):
    return extract(LoadedSpec(doc=doc, dialect=OPENAPI_3, version="3.0.3", source="t"), **kw)


def swagger2(doc, **kw):
    return extract(LoadedSpec(doc=doc, dialect=SWAGGER_2, version="2.0", source="t"), **kw)


# ---- OpenAPI 3.x ----------------------------------------------------------

def test_oas3_server_variable_substitution():
    doc = {
        "openapi": "3.0.0",
        "servers": [{"url": "https://{host}/v1", "variables": {"host": {"default": "api.x.com"}}}],
        "paths": {"/p": {"get": {}}},
    }
    model = oas3(doc)
    assert model.servers == ["https://api.x.com/v1"]


def test_oas3_params_classified():
    doc = {
        "openapi": "3.0.0",
        "paths": {
            "/users/{id}": {
                "get": {
                    "operationId": "getUser",
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}},
                        {"name": "q", "in": "query", "schema": {"type": "string"}},
                        {"name": "X-Trace", "in": "header", "schema": {"type": "string"}},
                    ],
                }
            }
        },
    }
    req = oas3(doc).requests[0]
    assert req.operation_id == "getUser"
    assert [p.name for p in req.path_params] == ["id"]
    assert [p.name for p in req.query_params] == ["q"]
    assert [p.name for p in req.header_params] == ["X-Trace"]


def test_oas3_path_level_params_merged():
    doc = {
        "openapi": "3.0.0",
        "paths": {
            "/x": {
                "parameters": [{"name": "common", "in": "query", "schema": {"type": "string"}}],
                "get": {"parameters": [{"name": "own", "in": "query", "schema": {"type": "string"}}]},
            }
        },
    }
    req = oas3(doc).requests[0]
    assert {p.name for p in req.query_params} == {"common", "own"}


def test_oas3_json_body():
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
    body = oas3(doc).requests[0].body
    assert body.kind == "json"
    assert body.value == {"name": "string"}


def test_oas3_array_body_becomes_raw():
    doc = {
        "openapi": "3.0.0",
        "paths": {
            "/u": {
                "post": {
                    "requestBody": {
                        "content": {"application/json": {"schema": {"type": "array", "items": {"type": "integer"}}}}
                    }
                }
            }
        },
    }
    body = oas3(doc).requests[0].body
    assert body.kind == "raw"
    assert body.raw == "[0]"


def test_oas3_form_and_multipart():
    doc = {
        "openapi": "3.0.0",
        "paths": {
            "/f": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/x-www-form-urlencoded": {
                                "schema": {"type": "object", "properties": {"a": {"type": "string"}}}
                            }
                        }
                    }
                }
            },
            "/m": {
                "post": {
                    "requestBody": {
                        "content": {
                            "multipart/form-data": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "file": {"type": "string", "format": "binary"},
                                        "note": {"type": "string"},
                                    },
                                }
                            }
                        }
                    }
                }
            },
        },
    }
    model = oas3(doc)
    form = next(r for r in model.requests if r.path == "/f").body
    mp = next(r for r in model.requests if r.path == "/m").body
    assert form.kind == "form"
    assert mp.kind == "multipart"
    assert mp.file_fields == ["file"]


def test_oas3_security_mapping():
    doc = {
        "openapi": "3.0.0",
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"},
                "basicAuth": {"type": "http", "scheme": "basic"},
                "apiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
            }
        },
        "paths": {
            "/b": {"get": {"security": [{"bearerAuth": []}]}},
            "/k": {"get": {"security": [{"apiKeyAuth": []}]}},
            "/basic": {"get": {"security": [{"basicAuth": []}]}},
        },
    }
    model = oas3(doc)
    by_path = {r.path: r for r in model.requests}
    assert by_path["/b"].security[0][0].kind == "bearer"
    assert by_path["/basic"].security[0][0].kind == "basic"
    ak = by_path["/k"].security[0][0]
    assert ak.kind == "apiKey" and ak.location == "header" and ak.param_name == "X-API-Key"


def test_oas3_global_security_applies():
    doc = {
        "openapi": "3.0.0",
        "security": [{"bearerAuth": []}],
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}},
        "paths": {"/x": {"get": {}}},
    }
    assert oas3(doc).requests[0].security[0][0].kind == "bearer"


def test_oas3_empty_security_requirement_is_optional():
    doc = {
        "openapi": "3.0.0",
        "security": [{"bearerAuth": []}],
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}},
        "paths": {"/public": {"get": {"security": [{}]}}},
    }
    assert oas3(doc).requests[0].security == []


# ---- Swagger 2.0 ----------------------------------------------------------

def test_swagger2_server_from_host_basepath_schemes():
    doc = {
        "swagger": "2.0",
        "schemes": ["https"],
        "host": "api.example.com",
        "basePath": "/v2",
        "paths": {"/p": {"get": {}}},
    }
    assert swagger2(doc).servers == ["https://api.example.com/v2"]


def test_swagger2_body_param():
    doc = {
        "swagger": "2.0",
        "paths": {
            "/u": {
                "post": {
                    "parameters": [
                        {
                            "name": "body",
                            "in": "body",
                            "schema": {"type": "object", "properties": {"name": {"type": "string"}}},
                        }
                    ]
                }
            }
        },
    }
    body = swagger2(doc).requests[0].body
    assert body.kind == "json" and body.value == {"name": "string"}


def test_swagger2_formdata_and_file():
    doc = {
        "swagger": "2.0",
        "consumes": ["multipart/form-data"],
        "paths": {
            "/upload": {
                "post": {
                    "parameters": [
                        {"name": "file", "in": "formData", "type": "file"},
                        {"name": "note", "in": "formData", "type": "string"},
                    ]
                }
            }
        },
    }
    body = swagger2(doc).requests[0].body
    assert body.kind == "multipart"
    assert body.file_fields == ["file"]


def test_swagger2_apikey_security():
    doc = {
        "swagger": "2.0",
        "securityDefinitions": {"api_key": {"type": "apiKey", "in": "header", "name": "api_key"}},
        "paths": {"/x": {"get": {"security": [{"api_key": []}]}}},
    }
    sc = swagger2(doc).requests[0].security[0][0]
    assert sc.kind == "apiKey" and sc.param_name == "api_key"


def test_swagger2_non_body_param_example_from_inline_type():
    doc = {
        "swagger": "2.0",
        "paths": {
            "/x": {
                "get": {
                    "parameters": [{"name": "limit", "in": "query", "type": "integer", "default": 10}]
                }
            }
        },
    }
    q = swagger2(doc).requests[0].query_params[0]
    assert q.value == 10
