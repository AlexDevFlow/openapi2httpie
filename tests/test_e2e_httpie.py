"""End-to-end behavioural test.

This is the test that proves the tool actually works: it generates a real
HTTPie script from a spec, then *runs it with the real ``http`` binary* against
a live in-process mock server, and asserts the server received exactly the
requests the spec describes — correct method, path, query string, auth header,
and JSON body. If HTTPie can't parse or send what we emit, this fails.
"""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from openapi2httpie.emitters.httpie import HttpieOptions, HttpieEmitter
from openapi2httpie.extract import extract
from openapi2httpie.loader import OPENAPI_3, LoadedSpec

HTTP_BIN = os.path.join(os.path.dirname(sys.executable), "http")
requires_httpie = pytest.mark.skipif(
    not os.path.exists(HTTP_BIN), reason="httpie 'http' binary not found in this environment"
)

SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "E2E", "version": "1"},
    "components": {
        "securitySchemes": {
            "bearerAuth": {"type": "http", "scheme": "bearer"},
            "apiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
        }
    },
    "paths": {
        "/users/{id}": {
            "get": {
                "operationId": "getUser",
                "parameters": [
                    {"name": "id", "in": "path", "required": True, "schema": {"type": "integer", "example": 42}},
                    {"name": "verbose", "in": "query", "schema": {"type": "boolean", "example": True}},
                ],
                "security": [{"bearerAuth": []}],
            },
            "delete": {
                "operationId": "deleteUser",
                "parameters": [
                    {"name": "id", "in": "path", "required": True, "schema": {"type": "integer", "example": 7}}
                ],
                "security": [{"bearerAuth": []}],
            },
        },
        "/users": {
            "post": {
                "operationId": "createUser",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["name", "age"],
                                "properties": {
                                    "name": {"type": "string", "example": "Ada Lovelace"},
                                    "age": {"type": "integer", "example": 36},
                                },
                            }
                        }
                    }
                },
                "security": [{"apiKeyAuth": []}],
            }
        },
    },
}


class _Recorder(BaseHTTPRequestHandler):
    log = []  # class-level; reset per test via fixture

    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        type(self).log.append(
            {
                "method": self.command,
                "path": self.path,
                "headers": {k.lower(): v for k, v in self.headers.items()},
                "body": body.decode("utf-8", "replace"),
            }
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    do_GET = do_POST = do_PUT = do_DELETE = _handle

    def log_message(self, *args):  # silence
        pass


@pytest.fixture
def server():
    _Recorder.log = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}", _Recorder.log
    finally:
        srv.shutdown()


@requires_httpie
def test_generated_script_hits_server_correctly(server, tmp_path):
    base_url, log = server
    model = extract(LoadedSpec(doc=SPEC, dialect=OPENAPI_3, version="3.0.0", source="t"))
    script = HttpieEmitter(HttpieOptions(base_url=base_url)).render_script(model)

    script_path = tmp_path / "run.sh"
    script_path.write_text(script)

    env = dict(os.environ)
    env["PATH"] = os.path.dirname(HTTP_BIN) + os.pathsep + env.get("PATH", "")
    env["BASE_URL"] = base_url
    env["TOKEN"] = "tok-123"
    env["X_API_KEY"] = "key-456"

    result = subprocess.run(
        ["bash", str(script_path)], env=env, capture_output=True, text=True, timeout=90
    )
    assert result.returncode == 0, f"script failed:\n{result.stderr}"

    # Three operations => three recorded requests.
    assert len(log) == 3, f"expected 3 requests, got {len(log)}: {log}"

    by_key = {(r["method"], r["path"].split("?")[0]): r for r in log}

    # GET /users/42?verbose=true with a bearer token.
    get = by_key[("GET", "/users/42")]
    assert "verbose=true" in get["path"]
    assert get["headers"].get("authorization") == "Bearer tok-123"

    # DELETE /users/7 with the same bearer token.
    delete = by_key[("DELETE", "/users/7")]
    assert delete["headers"].get("authorization") == "Bearer tok-123"

    # POST /users with the API key header and a correct JSON body.
    post = by_key[("POST", "/users")]
    assert post["headers"].get("x-api-key") == "key-456"
    assert post["headers"].get("content-type", "").startswith("application/json")
    assert json.loads(post["body"]) == {"name": "Ada Lovelace", "age": 36}


@requires_httpie
def test_offline_mode_does_not_send(server, tmp_path):
    base_url, log = server
    model = extract(LoadedSpec(doc=SPEC, dialect=OPENAPI_3, version="3.0.0", source="t"))
    script = HttpieEmitter(HttpieOptions(base_url=base_url, offline=True)).render_script(model)
    script_path = tmp_path / "offline.sh"
    script_path.write_text(script)

    env = dict(os.environ)
    env["PATH"] = os.path.dirname(HTTP_BIN) + os.pathsep + env.get("PATH", "")
    env["BASE_URL"] = base_url
    env["TOKEN"] = "t"
    env["X_API_KEY"] = "k"

    result = subprocess.run(
        ["bash", str(script_path)], env=env, capture_output=True, text=True, timeout=90
    )
    assert result.returncode == 0, result.stderr
    # --offline builds & prints requests but sends nothing.
    assert log == []
    # The printed output should contain the request lines.
    assert "GET /users/42" in result.stdout or "POST /users" in result.stdout
