# ADR-0018: IRIS exposes a LAN-only API surface for a paired Android app

## Status
Accepted — 2026-09-22

## Accepted — 2026-09-22
Implementation lands in `agent/mobile_auth.py` (the bearer middleware)
and `iris_api.py` (`POST /api/mobile/pair`). The LAN bind remains OFF
by default and is enabled only by the pairing flow. Mobile settings
live under `LAN_BIND_*` and `MOBILE_BEARER_HASH` in `agent.config`.

## Amends
ADR-0001 — IRIS is a single-user application bound to loopback.
The amendment here is narrow: IRIS binds to two interfaces, with
different authentication posture on each.

## Context
The owner has a Pixel 10a and wants an Android app that is the phone-side
counterpart to the IRIS web app: chat, journal entry, settings, insights
review, and sensor collection. State stays on the laptop; the phone is a
thin client. The phone must reach IRIS over the home Wi-Fi.

The cleanest answer would be a private tunnel (Tailscale, WireGuard)
that preserves ADR-0001's loopback invariant while letting the phone
reach the laptop. The owner has decided not to take that route.

The remaining option is to bind IRIS to the LAN interface directly. That
contradicts ADR-0001's letter; the right move is to amend it deliberately
and record what the amendment does and does not allow.

## Decision
IRIS binds to two interfaces:

- `127.0.0.1:8000` — the existing loopback. No authentication. No change.
- `<lan-interface>:8765` — a new bind, on the LAN interface only (not
  `0.0.0.0`, not `::`), on a configurable port. Bearer-token authentication
  is mandatory on this bind. The token is generated at first install of
  the Android app, displayed once, and entered into IRIS's settings
  (`POST /api/mobile/pair`); IRIS stores the SHA-256 hash.

All mobile routes live under `/api/mobile/*`. They are the only routes
that respond on the LAN bind. `/api/*` routes (the existing web surface)
also respond on the LAN bind, but only with the bearer.

## Consequences
The loopback invariant is *narrowed*, not removed. The trust boundary
moves from "the operating system" to "the home Wi-Fi plus a 256-bit
bearer". A device on the same Wi-Fi that does not have the bearer still
cannot reach IRIS.

The threat model changes. A passive observer on the same Wi-Fi can see
that IRIS is talking to a phone. Active attackers can attempt to
brute-force the bearer. Mitigations: the bearer is 256 bits of entropy;
the rate limiter on `/api/mobile/pair` caps guesses; the bearer is
rotatable from IRIS settings.

A separate ADR is required to widen the bind further (e.g., to allow
the bearer to expire and need a re-pair, or to introduce a short-lived
JWT). The point of this amendment is the LAN-bind itself, not the
authentication scheme.

## Risks
- The laptop's LAN IP changes when the network changes. The Android app
  asks for it at install and at every connect; the owner re-enters it
  when it changes. Mitigation: mDNS lookup of `iris.local` is a future
  follow-up, not part of this amendment.
- The bearer is the only thing standing between the phone and someone
  else on the Wi-Fi. Mitigation: the token is stored in the Android
  Keystore (hardware-backed when available) and is never written to
  logs or backups.
