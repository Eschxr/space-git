# ADR 0002: Use PGSTY Silo for local S3 storage

Status: accepted by the operator; Phase 1 integration validated.

## Context and decision

The implementation plan specified MinIO as the local S3 service. Its configured
server and client images became unavailable, blocking Phase 1. The operator
requested evaluation and appropriate adoption of [PGSTY Silo](https://github.com/pgsty/silo).
Use Silo as the local S3 service while retaining the storage contracts and Python
MinIO SDK. This is an approved infrastructure substitution to the plan, without
starting Phase 2 or changing camera/model architecture.

The project's [release README](https://github.com/pgsty/silo/tree/RELEASE.2026-11-12T00-00-00Z)
documents the S3 protocol, MINIO environment variables and health-route compatibility.
Its image bundles `mcli` and curl, as shown in the
[release Dockerfile](https://github.com/pgsty/silo/blob/RELEASE.2026-11-12T00-00-00Z/Dockerfile.goreleaser).
The fork is independently maintained and licensed
[AGPL-3.0-or-later](https://github.com/pgsty/silo/blob/RELEASE.2026-11-12T00-00-00Z/LICENSE),
with [notices](https://github.com/pgsty/silo/blob/RELEASE.2026-11-12T00-00-00Z/NOTICE).

## Deployment and compatibility evidence

Pin `docker.io/pgsty/silo:RELEASE.2026-11-12T00-00-00Z` to manifest digest
`sha256:c20d112390b9a9ce8c11b8af95ad35bcaa62f4759663c09c936cd8d2b511f329`.
Compose uses `silo` and `silo-init`; both use this image, overridable via `SILO_IMAGE`.
Bootstrap uses `mcli` to create the private bucket idempotently. Preserve the
`minio_data` volume name, loopback port bindings and existing S3 credentials.
No existing data migration was performed or certified. Keep the original plan as
the historical specification and record this approved substitution here.

The actual image started with a passing `/minio/health/live` healthcheck. Bootstrap
exited 0 and set private bucket access. The integration suite passed conditional
PutObject immutability (including concurrent writes), identical-write retries,
checksum verification, environment isolation and a presigned HTTP GET through the
existing Python SDK. These are storage compatibility checks, with no model inference
or model-quality claims. PostgreSQL migration and constraint checks also passed.
