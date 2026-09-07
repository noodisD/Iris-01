# ADR-0004: Deploy as one systemd service, not a container image

## Status
Accepted — 2026-09-06

## Context
The README recommended `docker-compose up --build` as the primary way to run
IRIS, and it could not work: the Dockerfile copied `poetry.lock`, deleted during
the uv migration, and `iris_frontend.html`, deleted with the legacy UI. It
pinned Postgres 16 against a host running 18, and published the API on
`0.0.0.0` — an unauthenticated single-user application bound to every interface.
`scripts/iris.service.example` pointed at a path that did not exist and started
the CLI rather than the API. A separate branch carried Kubernetes manifests with
`replicas: 2`, on top of a module-level connection pool and in-process state.

## Decision
One machine, one systemd service running `uvicorn iris_api:app` on
`127.0.0.1`. The Dockerfile, `.dockerignore` and `docker-compose.yml` were
deleted. PostgreSQL runs as a local container, which is the host distribution's
convention for database engines; the application itself is not containerised.

## Consequences
The deployment story is one file that can be read in a minute, and the
`0.0.0.0` exposure disappears with the image that created it (see ADR-0001).

Horizontal scaling is not available and would be incorrect anyway: the ingest
pipeline's identity handling and the in-process caches assume a single writer.
Multi-instance deployment requires revisiting ADR-0001 first.
