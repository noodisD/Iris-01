# ADR-0018: IRIS exposes a LAN-only API surface for a paired Android app

## Status
Accepted — 2026-09-22

## Implementation status
Implemented for the sensor collector. The API allow-list in this decision was
expanded by [ADR-0019](ADR-0019-phone-app-over-lan.md) for the native IRIS app:
the paired bearer now authorizes `/api/` except laptop-only pairing routes.
The unauthenticated web UI remains loopback-only. The Android collector still
pins the server's public key, keeps an outbox and sends only over Wi-Fi on the
laptop's local subnet.

## Amends
ADR-0001 — IRIS is a single-user application bound to loopback.
The amendment here is narrow: IRIS binds to two interfaces, with
different authentication posture on each.

## Context
The owner has a Pixel 10a and wants an Android app to collect live
measurements and deliver them to the IRIS laptop over home Wi-Fi. Chat,
journaling, settings and review remain in the laptop web app; the phone is
only an opt-in sensor collector.

The cleanest answer would be a private tunnel (Tailscale, WireGuard)
that preserves ADR-0001's loopback invariant while letting the phone
reach the laptop. The owner has decided not to take that route.
(Revisited in [ADR-0022](ADR-0022-reach-iris-over-tailscale.md): the phone
listener may now bind the laptop's Tailscale address.)

The remaining option is to bind IRIS to the LAN interface directly. That
contradicts ADR-0001's letter; the right move is to amend it deliberately
and record what the amendment does and does not allow.

## Decision
IRIS runs two listeners from one process:

- `127.0.0.1:8000` — the existing unauthenticated web UI and local API.
- `<private-LAN-IP>:8765` — explicitly configured, TLS-only mobile intake.
  `0.0.0.0`, public addresses and IPv6 binds are rejected. Only
  `GET /api/mobile/status` and `POST /api/mobile/sensor/intake` reach the
  application there; other API and web paths return 404.

The local Settings UI generates a 256-bit random token and calls loopback-only
`POST /api/mobile/pair`. IRIS stores its SHA-256 hash, never the bearer.
The owner scans a QR containing the LAN URL, SHA-256 server public-key pin and
one-time bearer. The phone checks the certificate's IP hostname and public key
before sending the bearer; the key remains private across certificate reissues
for new IPs. An address-only QR updates the URL without rotating the token.
A replacement token invalidates the old one; `POST /api/mobile/unpair` revokes
it immediately.
Loopback pairing mutations reject browser origins outside loopback, so a
remote web page cannot rotate or revoke the phone's bearer through the local UI.

## Consequences
The web UI remains inaccessible from the LAN. A passive Wi-Fi observer sees
only TLS metadata, not readings or bearer contents; an active peer cannot
impersonate IRIS without the pinned certificate. Network isolation and a
high-entropy bearer still matter: the mobile listener must not be exposed
to the public Internet. Intake has a 16 MiB request limit and rejects
unauthorized traffic before parsing. The browser's local settings route is
deliberately not bearer-accessible over LAN.

## Risks
- The laptop's private IP may change. The listener regenerates an IP-SAN
  certificate using the same private key; the owner scans the new address QR.
  No mDNS discovery is claimed.
- Losing the phone or its token gives an attacker access to the mobile
  intake until the owner disconnects it on the laptop. The bearer is
  Keystore-encrypted on the phone and excluded from Android backup.
