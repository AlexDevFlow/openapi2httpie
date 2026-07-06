"""Emit a Postman Collection v2.1.0 from the IR.

Tuned for HTTPie Desktop's importer (which is closed-source; field choices come
from HTTPie's published import-compatibility docs):

* native ``auth`` objects (``basic`` / ``bearer`` / ``apikey``) so the importer
  maps credentials instead of us hand-rolling an Authorization header;
* structured ``url`` (``host`` / ``path`` / ``query`` / ``variable``) so params
  import as real params;
* requests grouped into per-tag folders (HTTPie Desktop flattens these into
  ``Folder / Request`` breadcrumb names — which is exactly what we want);
* no file bodies / scripts / cookies, which the importer drops anyway.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..model import ApiModel, Body, Request, SecurityScheme

_SCHEMA_V21 = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"


class PostmanEmitter:
    def __init__(self, base_url: Optional[str] = None) -> None:
        self._base_url_override = base_url

    def render(self, model: ApiModel) -> str:
        return json.dumps(self.build(model), indent=2, default=str)

    def build(self, model: ApiModel) -> Dict[str, Any]:
        variables: Dict[str, str] = {}
        base_url = self._base_url_override or model.primary_server or "https://api.example.com"
        variables["baseUrl"] = base_url

        # Group requests by their first tag; untagged go to the root.
        folders: Dict[str, List[Dict[str, Any]]] = {}
        root_items: List[Dict[str, Any]] = []
        for req in model.requests:
            item = self._item(req, variables)
            tag = req.tags[0] if req.tags else None
            if tag:
                folders.setdefault(tag, []).append(item)
            else:
                root_items.append(item)

        items: List[Dict[str, Any]] = []
        for tag, tag_items in folders.items():
            items.append({"name": tag, "item": tag_items})
        items.extend(root_items)

        collection = {
            "info": {
                "name": model.title or "API",
                "description": model.description or "",
                "schema": _SCHEMA_V21,
                "_postman_id": _stable_id(model.title, model.version),
            },
            "item": items,
            "variable": [
                {"key": k, "value": v, "type": "string"} for k, v in variables.items()
            ],
        }
        return collection

    # -- items -------------------------------------------------------------

    def _item(self, req: Request, variables: Dict[str, str]) -> Dict[str, Any]:
        request: Dict[str, Any] = {
            "method": req.method,
            "header": self._headers(req),
            "url": self._url(req),
        }
        if req.description or req.summary:
            request["description"] = req.description or req.summary

        body = self._body(req.body)
        if body is not None:
            request["body"] = body

        if req.security:
            auth = self._auth(req.security[0], variables)
            if auth:
                request["auth"] = auth

        return {"name": req.label, "request": request}

    def _headers(self, req: Request) -> List[Dict[str, Any]]:
        headers = []
        for h in req.header_params:
            headers.append({"key": h.name, "value": _stringify(h.value)})
        # Declare Content-Type for bodies where it isn't implied by the mode.
        if req.body.kind in ("json", "raw"):
            ct = req.body.content_type or "application/json"
            if not any(h["key"].lower() == "content-type" for h in headers):
                headers.append({"key": "Content-Type", "value": ct})
        return headers

    def _url(self, req: Request) -> Dict[str, Any]:
        path = req.path if req.path.startswith("/") else "/" + req.path
        segments = [seg for seg in path.split("/") if seg != ""]
        pm_segments = [
            (":" + seg[1:-1]) if (seg.startswith("{") and seg.endswith("}")) else seg
            for seg in segments
        ]

        query = [{"key": q.name, "value": _stringify(q.value)} for q in req.query_params]
        variables = [
            {"key": pp.name, "value": _stringify(pp.value)} for pp in req.path_params
        ]

        raw = "{{baseUrl}}/" + "/".join(pm_segments)
        if query:
            raw += "?" + "&".join(f"{q['key']}={q['value']}" for q in query)

        url: Dict[str, Any] = {
            "raw": raw,
            "host": ["{{baseUrl}}"],
            "path": pm_segments,
        }
        if query:
            url["query"] = query
        if variables:
            url["variable"] = variables
        return url

    def _body(self, body: Body) -> Optional[Dict[str, Any]]:
        if body.kind == "none":
            return None
        if body.kind == "json":
            return {
                "mode": "raw",
                "raw": json.dumps(body.value, indent=2, default=str),
                "options": {"raw": {"language": "json"}},
            }
        if body.kind == "raw":
            return {"mode": "raw", "raw": body.raw or ""}
        if body.kind == "form":
            return {
                "mode": "urlencoded",
                "urlencoded": [
                    {"key": k, "value": _stringify(v)} for k, v in (body.value or {}).items()
                ],
            }
        if body.kind == "multipart":
            data = []
            for k, v in (body.value or {}).items():
                if k in body.file_fields:
                    data.append({"key": k, "type": "file", "src": []})
                else:
                    data.append({"key": k, "value": _stringify(v), "type": "text"})
            return {"mode": "formdata", "formdata": data}
        return None

    def _auth(self, schemes: List[SecurityScheme], variables: Dict[str, str]) -> Optional[Dict[str, Any]]:
        for sc in schemes:
            if sc.kind == "basic":
                variables.setdefault("username", "REPLACE_ME")
                variables.setdefault("password", "REPLACE_ME")
                return {
                    "type": "basic",
                    "basic": [
                        {"key": "username", "value": "{{username}}", "type": "string"},
                        {"key": "password", "value": "{{password}}", "type": "string"},
                    ],
                }
            if sc.kind in ("bearer", "oauth2", "openIdConnect"):
                variables.setdefault("token", "REPLACE_ME")
                return {
                    "type": "bearer",
                    "bearer": [{"key": "token", "value": "{{token}}", "type": "string"}],
                }
            if sc.kind == "apiKey":
                variables.setdefault("apiKey", "REPLACE_ME")
                return {
                    "type": "apikey",
                    "apikey": [
                        {"key": "key", "value": sc.param_name or "X-API-Key", "type": "string"},
                        {"key": "value", "value": "{{apiKey}}", "type": "string"},
                        {"key": "in", "value": sc.location or "header", "type": "string"},
                    ],
                }
        return None


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


def _stable_id(title: str, version: str) -> str:
    """A deterministic pseudo-UUID so re-runs produce identical collections."""
    import hashlib

    digest = hashlib.sha1(f"{title}:{version}".encode("utf-8")).hexdigest()
    return f"{digest[0:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"
