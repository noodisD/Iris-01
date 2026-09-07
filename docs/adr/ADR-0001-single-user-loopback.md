# ADR-0001: IRIS is a single-user application bound to loopback

## Status
Accepted — 2026-09-06

## Context
The codebase carried two authentication models at once. Twenty-four routes took
no credentials and resolved a hardcoded `local` user; seventeen took a JWT in
the query string. The same resource family was protected two different ways —
`GET /api/habits` wanted a token, `POST /api/habits` wanted nothing — and the
legacy HTML called `/api/habits/today?token=…`, a route that ignores the token,
so every logged-in user was served the same dataset.

The JWT half was also unfit for the multi-user product it implied: the signing
key defaulted to the literal `"your-secret-key-change-in-production"`, passwords
were unsalted single-round SHA-256, and tokens travelled in URLs, where they
land in access logs and browser history.

## Decision
IRIS is a personal, single-user application. It binds to `127.0.0.1`, has no
login, and resolves one local user. The JWT machinery, `/api/auth/*`,
`python-jose` and the password hashing were deleted rather than repaired.

## Consequences
The whole class of authentication defects is gone by removal rather than by
patching. CORS is unnecessary, since one process serves both the API and the
SPA from the same origin.

Exposing IRIS on a network is now a security incident, not a configuration
option. Anything that would publish it — a container image, a reverse proxy, a
non-loopback bind — must first restore a real authentication story, which means
revisiting this ADR rather than working around it.
