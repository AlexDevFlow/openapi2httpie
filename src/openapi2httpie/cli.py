"""Command-line interface for openapi2httpie."""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import List, Optional

from . import __version__
from .emitters.httpie import HttpieEmitter, HttpieOptions
from .emitters.postman import PostmanEmitter
from .errors import OpenAPI2HTTPieError
from .extract import extract
from .loader import load
from .model import ApiModel, Request


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="openapi2httpie",
        description="Convert an OpenAPI/Swagger spec into runnable HTTPie commands "
        "or a Postman collection you can import into HTTPie Desktop.",
    )
    p.add_argument("spec", help="path to an OpenAPI/Swagger file, a URL, or - for stdin")
    p.add_argument(
        "-f", "--format", choices=("httpie", "postman"), default="httpie",
        help="output format (default: httpie)",
    )
    p.add_argument(
        "-o", "--output", metavar="PATH",
        help="write to PATH (default: stdout). With --split, PATH is a directory.",
    )
    p.add_argument(
        "--split", action="store_true",
        help="httpie only: write one script per operation into the output directory",
    )
    p.add_argument("--base-url", metavar="URL", help="override the base URL from the spec")
    p.add_argument(
        "--offline", action="store_true",
        help="emit 'http --offline' commands (build and print the request, don't send)",
    )
    p.add_argument(
        "--command", choices=("http", "https"), default="http",
        help="HTTPie executable name to emit (default: http)",
    )
    p.add_argument(
        "--all-optional", action="store_true",
        help="include optional parameters and body properties in generated examples",
    )
    p.add_argument("--no-auth", action="store_true", help="do not emit authentication")
    p.add_argument(
        "--no-multiline", action="store_true",
        help="keep each command on a single line",
    )
    p.add_argument(
        "--tag", action="append", metavar="TAG", default=[],
        help="only include operations with this tag (repeatable)",
    )
    p.add_argument(
        "--operation", action="append", metavar="ID", default=[],
        help="only include this operationId (repeatable)",
    )
    p.add_argument("--version", action="version", version=f"openapi2httpie {__version__}")
    return p


def _filter_requests(model: ApiModel, tags: List[str], ops: List[str]) -> None:
    if not tags and not ops:
        return
    tagset, opset = set(tags), set(ops)
    kept: List[Request] = []
    for req in model.requests:
        if opset and req.operation_id in opset:
            kept.append(req)
        elif tagset and tagset.intersection(req.tags):
            kept.append(req)
    model.requests = kept


def _slug(req: Request, index: int) -> str:
    base = req.operation_id or f"{req.method}_{req.path}"
    slug = re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_").lower()
    return f"{index:03d}_{slug or 'request'}"


def _write(path: Optional[str], text: str) -> None:
    if path is None:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        return
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        model = extract(load(args.spec), include_optional=args.all_optional)
    except OpenAPI2HTTPieError as exc:
        print(f"openapi2httpie: {exc}", file=sys.stderr)
        return 2

    _filter_requests(model, args.tag, args.operation)
    if not model.requests:
        print("openapi2httpie: no operations matched (check --tag/--operation)", file=sys.stderr)
        return 1

    if args.format == "postman":
        if args.split:
            print("openapi2httpie: --split is only supported for --format httpie", file=sys.stderr)
            return 2
        emitter = PostmanEmitter(base_url=args.base_url)
        _write(args.output, emitter.render(model))
        return 0

    # httpie
    options = HttpieOptions(
        command=args.command,
        base_url=args.base_url,
        offline=args.offline,
        multiline=not args.no_multiline,
        include_auth=not args.no_auth,
    )
    emitter = HttpieEmitter(options)

    if args.split:
        out_dir = args.output or "."
        os.makedirs(out_dir, exist_ok=True)
        for index, req in enumerate(model.requests, start=1):
            single = ApiModel(
                title=model.title, version=model.version, description=model.description,
                servers=model.servers, requests=[req],
            )
            fname = os.path.join(out_dir, _slug(req, index) + ".sh")
            with open(fname, "w", encoding="utf-8") as fh:
                fh.write(emitter.render_script(single))
        print(f"openapi2httpie: wrote {len(model.requests)} scripts to {out_dir}", file=sys.stderr)
        return 0

    _write(args.output, emitter.render_script(model))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
