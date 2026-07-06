"""Normalise a loaded Swagger 2.0 / OpenAPI 3.x document into the IR
(:class:`~openapi2httpie.model.ApiModel`)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .examples import ExampleBuilder
from .loader import OPENAPI_3, SWAGGER_2, LoadedSpec
from .model import ApiModel, Body, Param, Request, SecurityScheme
from .resolver import Resolver

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


def extract(spec: LoadedSpec, include_optional: bool = False) -> ApiModel:
    """Build an :class:`ApiModel` from a loaded spec."""
    resolver = Resolver(spec.doc)
    builder = ExampleBuilder(resolver, include_optional=include_optional)
    if spec.dialect == OPENAPI_3:
        return _Extractor(spec.doc, resolver, builder, is_v2=False).run()
    if spec.dialect == SWAGGER_2:
        return _Extractor(spec.doc, resolver, builder, is_v2=True).run()
    raise ValueError(f"unknown dialect {spec.dialect!r}")


def _is_json_media(content_type: str) -> bool:
    return "json" in content_type.lower()


class _Extractor:
    def __init__(self, doc: Dict[str, Any], resolver: Resolver, builder: ExampleBuilder, is_v2: bool):
        self.doc = doc
        self.resolver = resolver
        self.builder = builder
        self.is_v2 = is_v2
        self.schemes: Dict[str, SecurityScheme] = self._security_schemes()
        self.global_security: List[Dict[str, Any]] = doc.get("security", []) or []

    # -- entry -------------------------------------------------------------

    def run(self) -> ApiModel:
        info = self.doc.get("info", {}) or {}
        servers = self._servers()
        requests: List[Request] = []
        for path, path_item in (self.doc.get("paths", {}) or {}).items():
            if not isinstance(path_item, dict):
                continue
            path_item = self.resolver.deref(path_item)
            common_params = path_item.get("parameters", []) or []
            for method in HTTP_METHODS:
                op = path_item.get(method)
                if not isinstance(op, dict):
                    continue
                requests.append(
                    self._operation(method.upper(), path, op, common_params, servers[0])
                )
        return ApiModel(
            title=info.get("title", "API"),
            version=info.get("version", ""),
            description=info.get("description", ""),
            servers=servers,
            requests=requests,
        )

    # -- servers -----------------------------------------------------------

    def _servers(self) -> List[str]:
        if self.is_v2:
            schemes = self.doc.get("schemes") or ["https"]
            host = self.doc.get("host", "")
            base_path = self.doc.get("basePath", "") or ""
            if host:
                return [f"{schemes[0]}://{host}{base_path}"]
            return [base_path or "/"]
        servers = self.doc.get("servers") or []
        urls = []
        for s in servers:
            if not isinstance(s, dict):
                continue
            url = s.get("url", "/")
            # Substitute OpenAPI 3.x server-variable defaults so the URL is real.
            for var, spec in (s.get("variables") or {}).items():
                if isinstance(spec, dict) and "default" in spec:
                    url = url.replace("{" + var + "}", str(spec["default"]))
            urls.append(url)
        return urls or ["/"]

    # -- security ----------------------------------------------------------

    def _security_schemes(self) -> Dict[str, SecurityScheme]:
        out: Dict[str, SecurityScheme] = {}
        if self.is_v2:
            defs = self.doc.get("securityDefinitions", {}) or {}
            for name, node in defs.items():
                out[name] = self._swagger2_scheme(name, node)
        else:
            comps = (self.doc.get("components", {}) or {}).get("securitySchemes", {}) or {}
            for name, node in comps.items():
                node = self.resolver.deref(node)
                out[name] = self._oas3_scheme(name, node)
        return out

    @staticmethod
    def _swagger2_scheme(name: str, node: Dict[str, Any]) -> SecurityScheme:
        t = node.get("type")
        if t == "basic":
            return SecurityScheme(name=name, kind="basic", description=node.get("description", ""))
        if t == "apiKey":
            return SecurityScheme(
                name=name, kind="apiKey", location=node.get("in"),
                param_name=node.get("name"), description=node.get("description", ""),
            )
        return SecurityScheme(name=name, kind=t or "oauth2", description=node.get("description", ""))

    @staticmethod
    def _oas3_scheme(name: str, node: Dict[str, Any]) -> SecurityScheme:
        t = node.get("type")
        if t == "http":
            scheme = (node.get("scheme") or "").lower()
            kind = "bearer" if scheme == "bearer" else "basic" if scheme == "basic" else scheme or "basic"
            return SecurityScheme(
                name=name, kind=kind, bearer_format=node.get("bearerFormat"),
                description=node.get("description", ""),
            )
        if t == "apiKey":
            return SecurityScheme(
                name=name, kind="apiKey", location=node.get("in"),
                param_name=node.get("name"), description=node.get("description", ""),
            )
        return SecurityScheme(name=name, kind=t or "oauth2", description=node.get("description", ""))

    def _map_security(self, requirements: List[Dict[str, Any]]) -> List[List[SecurityScheme]]:
        out: List[List[SecurityScheme]] = []
        for req in requirements:
            if not req:  # empty {} => auth optional; skip
                continue
            anded = [self.schemes[n] for n in req.keys() if n in self.schemes]
            if anded:
                out.append(anded)
        return out

    # -- operation ---------------------------------------------------------

    def _operation(
        self,
        method: str,
        path: str,
        op: Dict[str, Any],
        common_params: List[Any],
        server: str,
    ) -> Request:
        # Merge path-level and operation-level parameters; operation wins on
        # (name, in) collisions.
        merged: Dict[tuple, Any] = {}
        for raw in list(common_params) + list(op.get("parameters", []) or []):
            p = self.resolver.deref(raw)
            merged[(p.get("name"), p.get("in"))] = p

        path_params: List[Param] = []
        query_params: List[Param] = []
        header_params: List[Param] = []
        cookie_pairs: List[str] = []
        form_params: List[Any] = []
        body_param: Optional[Dict[str, Any]] = None

        for p in merged.values():
            loc = p.get("in")
            if loc == "body":  # swagger 2.0 body param
                body_param = p
                continue
            if loc == "formData":  # swagger 2.0 form param
                form_params.append(p)
                continue
            value = self._param_example(p)
            param = Param(
                name=p.get("name", ""), location=loc, value=value,
                required=bool(p.get("required", loc == "path")),
                description=p.get("description", ""),
            )
            if loc == "path":
                path_params.append(param)
            elif loc == "query":
                query_params.append(param)
            elif loc == "header":
                header_params.append(param)
            elif loc == "cookie":
                cookie_pairs.append(f"{param.name}={_stringify(param.value)}")

        if cookie_pairs:
            header_params.append(
                Param(name="Cookie", location="header", value="; ".join(cookie_pairs), required=False)
            )

        body = self._body(op, body_param, form_params)

        requirements = op.get("security", self.global_security)
        security = self._map_security(requirements if requirements is not None else [])

        return Request(
            method=method,
            path=path,
            server_url=server,
            operation_id=op.get("operationId", ""),
            summary=op.get("summary", ""),
            description=op.get("description", ""),
            tags=list(op.get("tags", []) or []),
            path_params=path_params,
            query_params=query_params,
            header_params=header_params,
            body=body,
            security=security,
            deprecated=bool(op.get("deprecated", False)),
        )

    def _param_example(self, p: Dict[str, Any]) -> Any:
        if "example" in p:
            return p["example"]
        examples = p.get("examples")
        if isinstance(examples, dict) and examples:
            first = next(iter(examples.values()))
            if isinstance(first, dict) and "value" in first:
                return first["value"]
            return first
        if "schema" in p:  # OpenAPI 3.x
            return self.builder.build(p["schema"])
        return self.builder.build(p)  # Swagger 2.0: type/format live on the param

    # -- body --------------------------------------------------------------

    def _body(
        self,
        op: Dict[str, Any],
        body_param: Optional[Dict[str, Any]],
        form_params: List[Any],
    ) -> Body:
        if self.is_v2:
            return self._body_v2(op, body_param, form_params)
        return self._body_v3(op)

    def _body_v2(self, op, body_param, form_params) -> Body:
        if body_param is not None:
            value = None
            if "example" in body_param:
                value = body_param["example"]
            elif "schema" in body_param:
                value = self.builder.build(body_param["schema"])
            return self._json_or_raw(value, "application/json")
        if form_params:
            consumes = op.get("consumes") or self.doc.get("consumes") or []
            is_multipart = any("multipart" in c for c in consumes) or any(
                p.get("type") == "file" for p in form_params
            )
            fields: Dict[str, Any] = {}
            files: List[str] = []
            for p in form_params:
                name = p.get("name", "")
                if p.get("type") == "file":
                    files.append(name)
                    fields[name] = ""
                else:
                    fields[name] = self.builder.build(p)
            if is_multipart:
                return Body(kind="multipart", value=fields, file_fields=files,
                            content_type="multipart/form-data")
            return Body(kind="form", value=fields, content_type="application/x-www-form-urlencoded")
        return Body()

    def _body_v3(self, op) -> Body:
        rb = op.get("requestBody")
        if not rb:
            return Body()
        rb = self.resolver.deref(rb)
        content = rb.get("content", {}) or {}
        if not content:
            return Body()

        json_key = next((k for k in content if _is_json_media(k)), None)
        if json_key:
            value = self._media_example(content[json_key])
            return self._json_or_raw(value, json_key)

        if "application/x-www-form-urlencoded" in content:
            media = content["application/x-www-form-urlencoded"]
            value = self._media_example(media)
            return Body(kind="form", value=value if isinstance(value, dict) else {},
                        content_type="application/x-www-form-urlencoded")

        if "multipart/form-data" in content:
            media = content["multipart/form-data"]
            value = self._media_example(media)
            files = self._detect_file_fields(media.get("schema"))
            return Body(kind="multipart", value=value if isinstance(value, dict) else {},
                        file_fields=files, content_type="multipart/form-data")

        # Fallback: first declared media type, sent raw.
        key = next(iter(content))
        value = self._media_example(content[key])
        if _is_json_media(key):
            return self._json_or_raw(value, key)
        raw = value if isinstance(value, str) else json.dumps(value, default=str)
        return Body(kind="raw", raw=raw, content_type=key)

    def _media_example(self, media: Dict[str, Any]) -> Any:
        if not isinstance(media, dict):
            return None
        if "example" in media:
            return media["example"]
        examples = media.get("examples")
        if isinstance(examples, dict) and examples:
            first = next(iter(examples.values()))
            first = self.resolver.deref(first)
            if isinstance(first, dict) and "value" in first:
                return first["value"]
            return first
        if "schema" in media:
            return self.builder.build(media["schema"])
        return None

    @staticmethod
    def _json_or_raw(value: Any, content_type: str) -> Body:
        # A JSON object maps cleanly to editable HTTPie items; anything else
        # (array, scalar, null) has to travel as a raw body.
        if isinstance(value, dict):
            return Body(kind="json", value=value, content_type=content_type)
        raw = value if isinstance(value, str) else json.dumps(value, default=str)
        return Body(kind="raw", raw=raw, content_type=content_type)

    def _detect_file_fields(self, schema: Any) -> List[str]:
        schema = self.resolver.deref(schema) if schema else None
        if not isinstance(schema, dict):
            return []
        files = []
        for name, prop in (schema.get("properties", {}) or {}).items():
            prop = self.resolver.deref(prop)
            if isinstance(prop, dict) and prop.get("type") == "string" and prop.get("format") in ("binary", "byte"):
                files.append(name)
        return files


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)
