"""Smoke tests against the real Swagger Petstore specs (2.0 and 3.0)."""

import json
import os
import shutil
import subprocess

import pytest

from openapi2httpie import build_model
from openapi2httpie.emitters.httpie import HttpieEmitter
from openapi2httpie.emitters.postman import PostmanEmitter

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
SPECS = [
    os.path.join(FIXTURES, "petstore_oas3.json"),
    os.path.join(FIXTURES, "petstore_swagger2.json"),
]
AVAILABLE = [s for s in SPECS if os.path.exists(s)]


@pytest.mark.parametrize("spec", AVAILABLE, ids=[os.path.basename(s) for s in AVAILABLE])
@pytest.mark.skipif(not shutil.which("bash"), reason="bash not available")
def test_httpie_output_is_valid_bash(spec, tmp_path):
    model = build_model(spec)
    assert model.requests, "expected at least one operation"
    script = HttpieEmitter().render_script(model)
    path = tmp_path / "out.sh"
    path.write_text(script)
    # bash -n validates syntax without executing — the authoritative check that
    # our quoting is correct even for multi-line example values.
    result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("spec", AVAILABLE, ids=[os.path.basename(s) for s in AVAILABLE])
def test_postman_output_is_valid_and_structured(spec):
    model = build_model(spec)
    col = PostmanEmitter().build(model)
    text = json.dumps(col)  # must serialise
    assert json.loads(text)
    assert col["info"]["schema"].endswith("v2.1.0/collection.json")

    def walk(items):
        for it in items:
            if "item" in it:
                yield from walk(it["item"])
            elif "request" in it:
                yield it["request"]

    reqs = list(walk(col["item"]))
    assert reqs, "expected at least one request"
    for r in reqs:
        assert r["method"]
        assert r["url"]["raw"].startswith("{{baseUrl}}")


def test_petstore_specs_exist():
    # Guardrail: if fixtures vanish, make it loud rather than silently skipping.
    assert AVAILABLE, "no petstore fixtures found; run the fixture download"
