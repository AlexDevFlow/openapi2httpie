import json

from openapi2httpie.cli import main

SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "CLI Test", "version": "1"},
    "paths": {
        "/pets": {"get": {"operationId": "listPets", "tags": ["Pets"]}},
        "/orders": {"get": {"operationId": "listOrders", "tags": ["Orders"]}},
    },
}


def write_spec(tmp_path):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(SPEC))
    return str(p)


def test_httpie_to_stdout(tmp_path, capsys):
    rc = main([write_spec(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "http --ignore-stdin GET" in out
    assert out.startswith("#!/usr/bin/env bash")


def test_postman_to_file(tmp_path):
    out = tmp_path / "col.json"
    rc = main([write_spec(tmp_path), "-f", "postman", "-o", str(out)])
    assert rc == 0
    data = json.loads(out.read_text())
    assert data["info"]["schema"].endswith("v2.1.0/collection.json")


def test_filter_by_tag(tmp_path, capsys):
    rc = main([write_spec(tmp_path), "--tag", "Pets"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "/pets" in out
    assert "/orders" not in out


def test_filter_by_operation(tmp_path, capsys):
    main([write_spec(tmp_path), "--operation", "listOrders"])
    out = capsys.readouterr().out
    assert "/orders" in out and "/pets" not in out


def test_no_match_returns_1(tmp_path, capsys):
    rc = main([write_spec(tmp_path), "--tag", "Nonexistent"])
    assert rc == 1


def test_split_writes_files(tmp_path):
    out_dir = tmp_path / "scripts"
    rc = main([write_spec(tmp_path), "--split", "-o", str(out_dir)])
    assert rc == 0
    files = sorted(p.name for p in out_dir.glob("*.sh"))
    assert len(files) == 2
    assert files[0].startswith("001_")


def test_bad_spec_returns_2(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text('{"nope": true}')
    rc = main([str(bad)])
    assert rc == 2
    assert "openapi2httpie:" in capsys.readouterr().err


def test_split_rejected_for_postman(tmp_path, capsys):
    rc = main([write_spec(tmp_path), "-f", "postman", "--split"])
    assert rc == 2


def test_base_url_override(tmp_path, capsys):
    main([write_spec(tmp_path), "--base-url", "https://my.api"])
    out = capsys.readouterr().out
    assert "https://my.api" in out
