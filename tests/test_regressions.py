"""Regressions for bugs found by stress-testing against real specs."""

import json
import shutil
import subprocess

import pytest

from openapi2httpie.emitters.httpie import HttpieEmitter
from openapi2httpie.emitters.postman import PostmanEmitter
from openapi2httpie.extract import extract
from openapi2httpie.loader import parse_text, detect_dialect, LoadedSpec


def _model_from_yaml(text):
    doc = parse_text(text)  # exercises the real YAML path
    dialect, version = detect_dialect(doc)
    return extract(LoadedSpec(doc=doc, dialect=dialect, version=version, source="t"))


def test_yaml_date_example_does_not_become_datetime():
    # Bare YAML dates used to parse to datetime.date and crash json.dumps.
    spec = """
openapi: 3.0.0
info: { title: Dates, version: "1" }
paths:
  /events:
    post:
      requestBody:
        content:
          application/json:
            schema:
              type: object
              required: [start]
              properties:
                start: { type: string, example: 2020-01-01 }
"""
    model = _model_from_yaml(spec)
    body = model.requests[0].body
    assert body.value == {"start": "2020-01-01"}
    # Both emitters must serialise without error.
    HttpieEmitter().render_script(model)
    json.loads(PostmanEmitter().render(model))


@pytest.mark.skipif(not shutil.which("bash"), reason="bash not available")
def test_multiline_string_body_is_valid_bash(tmp_path):
    # A multi-line example value (e.g. a cloud-init script) must still yield a
    # syntactically valid bash script.
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "Multiline", "version": "1"},
        "paths": {
            "/droplets": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["user_data"],
                                    "properties": {
                                        "user_data": {
                                            "type": "string",
                                            "example": "#cloud-config\nruncmd:\n  - touch /test.txt\n",
                                        }
                                    },
                                }
                            }
                        }
                    }
                }
            }
        },
    }
    model = extract(LoadedSpec(doc=spec, dialect="openapi3", version="3.0.0", source="t"))
    script = HttpieEmitter().render_script(model)
    path = tmp_path / "ml.sh"
    path.write_text(script)
    result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
