# API

Implemented in Phase 0: `GET /health/live` → HTTP 200, `{"status":"ok"}`.
OpenAPI is available at `/openapi.json` and interactive documentation at `/docs`.
Liveness does not probe infrastructure or pretrained models. No business endpoints
or readiness endpoint exist yet. The planned versioned API is specified in
`CODEX_IMPLEMENTATION_PLAN.md`; it is not yet implemented.
