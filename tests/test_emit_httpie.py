import shlex

from openapi2httpie.emitters.httpie import HttpieEmitter, HttpieOptions, env_name
from openapi2httpie.extract import extract
from openapi2httpie.loader import OPENAPI_3, LoadedSpec


def render(doc, **opts):
    model = extract(LoadedSpec(doc=doc, dialect=OPENAPI_3, version="3.0.3", source="t"))
    return HttpieEmitter(HttpieOptions(**opts)).render_script(model)


def one_command(doc, **opts):
    model = extract(LoadedSpec(doc=doc, dialect=OPENAPI_3, version="3.0.3", source="t"))
    return HttpieEmitter(HttpieOptions(**opts)).render_commands(model)[0][1]


def test_env_name_sanitizes():
    assert env_name("X-API-Key") == "X_API_KEY"
    assert env_name("api key!") == "API_KEY"
    assert env_name("123") == "_123"


def test_header_and_env_block():
    doc = {"openapi": "3.0.0", "servers": [{"url": "https://x.io"}], "paths": {"/p": {"get": {}}}}
    out = render(doc)
    assert out.startswith("#!/usr/bin/env bash")
    assert ': "${BASE_URL:=https://x.io}"' in out


def test_get_with_query_and_path():
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
    cmd = one_command(doc)
    assert 'GET "$BASE_URL/users/0"' in cmd
    assert "q==string" in cmd


def test_bearer_auth():
    doc = {
        "openapi": "3.0.0",
        "components": {"securitySchemes": {"b": {"type": "http", "scheme": "bearer"}}},
        "paths": {"/x": {"get": {"security": [{"b": []}]}}},
    }
    cmd = one_command(doc)
    assert '-A bearer -a "$TOKEN"' in cmd


def test_basic_auth():
    doc = {
        "openapi": "3.0.0",
        "components": {"securitySchemes": {"b": {"type": "http", "scheme": "basic"}}},
        "paths": {"/x": {"get": {"security": [{"b": []}]}}},
    }
    cmd = one_command(doc)
    assert '-a "$USERNAME:$PASSWORD"' in cmd


def test_apikey_header_query_cookie():
    def mk(loc):
        return {
            "openapi": "3.0.0",
            "components": {"securitySchemes": {"k": {"type": "apiKey", "in": loc, "name": "Key"}}},
            "paths": {"/x": {"get": {"security": [{"k": []}]}}},
        }

    assert '"Key:$KEY"' in one_command(mk("header"))
    assert '"Key==$KEY"' in one_command(mk("query"))
    assert '"Cookie:Key=$KEY"' in one_command(mk("cookie"))


def test_json_body_items():
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
                                    "required": ["name", "age", "active"],
                                    "properties": {
                                        "name": {"type": "string", "example": "Ada"},
                                        "age": {"type": "integer"},
                                        "active": {"type": "boolean"},
                                    },
                                }
                            }
                        }
                    }
                }
            }
        },
    }
    cmd = one_command(doc)
    assert "name=Ada" in cmd
    assert "age:=0" in cmd
    assert "active:=true" in cmd


def test_raw_body_for_non_json_content():
    doc = {
        "openapi": "3.0.0",
        "paths": {
            "/x": {
                "post": {
                    "requestBody": {
                        "content": {"text/plain": {"schema": {"type": "string", "example": "hello"}}}
                    }
                }
            }
        },
    }
    cmd = one_command(doc)
    assert "--raw=hello" in cmd
    assert "Content-Type:text/plain" in cmd


def test_offline_flag():
    doc = {"openapi": "3.0.0", "paths": {"/x": {"get": {}}}}
    cmd = one_command(doc, offline=True)
    assert cmd.startswith("http --ignore-stdin --offline GET")


def test_ignore_stdin_default_on_and_toggle():
    doc = {"openapi": "3.0.0", "paths": {"/x": {"get": {}}}}
    assert one_command(doc).startswith("http --ignore-stdin GET")
    assert "--ignore-stdin" not in one_command(doc, ignore_stdin=False)


def test_no_auth_option():
    doc = {
        "openapi": "3.0.0",
        "components": {"securitySchemes": {"b": {"type": "http", "scheme": "bearer"}}},
        "paths": {"/x": {"get": {"security": [{"b": []}]}}},
    }
    cmd = one_command(doc, include_auth=False)
    assert "bearer" not in cmd


def test_values_with_spaces_are_quoted_safely():
    doc = {
        "openapi": "3.0.0",
        "paths": {
            "/x": {
                "get": {
                    "parameters": [
                        {"name": "q", "in": "query", "schema": {"type": "string", "example": "a b; rm -rf"}}
                    ]
                }
            }
        },
    }
    cmd = one_command(doc)
    # The whole item must survive as a single shell token.
    tokens = shlex.split(cmd)
    assert "q==a b; rm -rf" in tokens


def test_command_name_https():
    doc = {"openapi": "3.0.0", "paths": {"/x": {"get": {}}}}
    assert one_command(doc, command="https").startswith("https --ignore-stdin GET")
