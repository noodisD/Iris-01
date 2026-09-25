# ADR-0019: The paired phone uses the LAN API as a native IRIS app

## Status
Accepted — 2026-09-24

## Amends
ADR-0001 and ADR-0018. The loopback web UI and pairing authority remain unchanged; the paired phone's pinned-TLS bearer now authorizes the full `/api/` surface on the private-LAN listener.

## Context
The Android collector needs to become a native IRIS app, including chat, journal, imports, insights and settings. The old LAN allow-list only admitted mobile status and sensor intake. A WebView is not the chosen UI. The laptop remains the pairing authority and the phone reaches it over home Wi-Fi.

## Decision
Serve `/api/` requests through the existing bearer gate on the TLS LAN listener, except `GET /api/mobile/connection`, `POST /api/mobile/pair` and `POST /api/mobile/unpair`: those stay loopback-only. The web UI, assets, health route and SPA fallback are never served from the LAN listener. Preserve the TLS requirement, explicit private-LAN bind, token hash check, rejection history and the Android public-key pin and Wi-Fi binding. The phone authenticates its user with the device fingerprint or screen lock on opening and after five minutes in the background; the collector still runs independently while the UI is locked.

## Consequences
The bearer now grants access to private writing and all user API actions, not only sensor intake. Losing the paired phone or exposing the token requires revocation from laptop Settings. Keep the listener restricted to the home network; no public bind or unpinned fallback. The laptop's unauthenticated web UI must stay bound to loopback and the phone cannot mint, rotate or revoke its own bearer. Future `/api/` endpoints are accessible to a paired phone by default unless specifically restricted.
