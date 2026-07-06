# Changelog

## 0.1.0 — unreleased

Initial release.

- Convert Swagger 2.0 and OpenAPI 3.0/3.1 specs to runnable HTTPie commands.
- Faithful auth mapping: HTTP basic, bearer, apiKey (header/query/cookie),
  oauth2/openIdConnect (as bearer), from `securitySchemes` and per-operation
  `security`.
- Example bodies from spec `example`/`examples`/`default`/`enum`, with
  type- and format-aware fallbacks; `allOf`/`oneOf`/`anyOf` support;
  cycle- and depth-safe for recursive schemas.
- Postman Collection v2.1 output tuned for HTTPie Desktop import.
- CLI: format/output selection, `--split`, tag/operation filters, `--offline`,
  `--base-url`, `--all-optional`.
- `--ignore-stdin` by default so generated scripts run non-interactively.
