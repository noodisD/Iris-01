# ADR-0022: IRIS is reachable away from home over the owner's Tailscale network

## Status
Accepted — 2026-09-25

## Amends
ADR-0001, ADR-0018 and ADR-0019. It supersedes ADR-0018's decision not to use
a private tunnel. Everything else in those decisions stands: the pinned TLS
listener, the bearer, laptop-only pairing, and the unauthenticated web UI
never leaving loopback.

## Context
IRIS runs on the laptop, and the phone reached it only over the home Wi-Fi they
share. Away from home, neither the phone app nor the web UI worked. The owner
wants both to work everywhere, for their own devices only, with the laptop
still the server.

ADR-0018 named a private tunnel as the cleanest answer and declined it at the
time. The laptop and the phone are now both in the owner's Tailscale network
(a WireGuard mesh in which each device gets an address in `100.64.0.0/10` and
only devices signed in to the owner's account can connect). Nothing is exposed
to the public Internet.

## Decision
**The phone app** keeps its listener, TLS, pin and bearer exactly as they are,
and binds it to the laptop's Tailscale address instead of its home-network
address. `LAN_BIND_HOST` accepts `100.64.0.0/10` alongside the RFC 1918 ranges.
Public addresses and wildcards are still refused. The certificate is reissued
for the new address with the same key, so the phone's pin stays valid. The
phone sends over the Tailscale VPN on any carrier, including mobile data. For a
home-network address it still requires the Wi-Fi on the laptop's subnet. The
laptop firewall admits the listener's port on the `tailscale0` interface only.

**The web UI** is published inside the tailnet with `tailscale serve`, which
terminates HTTPS with a certificate for the laptop's tailnet name and proxies to
a dedicated loopback door, `127.0.0.1:TAILNET_PORT` (8001 by default). That door
opens only when `TAILNET_OWNERS` is set. Every request through it is tagged, and
admitted only if it carries exactly one `Tailscale-User-Login` header whose value
is in `TAILNET_OWNERS`. `serve` sets that header from the connecting device's
identity and removes any copy the client sent. Requests without it are refused,
including those from tagged devices, which carry no user. So are requests on an
unset owner list. Pairing, unpairing and the connection route return 404 there,
as they do on the phone listener: the phone's credentials are handed out only at
the laptop.

A login header arriving on the plain `127.0.0.1:8000` door is refused, because it
means `serve` was pointed at the port where the owner check does not run.

**Tailscale Funnel, which publishes to the public Internet, is never used.**

## Consequences
The owner reaches IRIS from anywhere their devices are signed in to Tailscale,
while the laptop is awake and IRIS is running. The laptop remains the only server
and the only copy of the data.

Trust now extends to the owner's Tailscale account. Anyone who can sign in as the
owner, or add a device to the tailnet under the owner's login, reaches the web UI
without a further password. The account's security, including two-factor sign-in
and device approval, is part of IRIS's security. A shared tailnet would need
`TAILNET_OWNERS` kept to the owner's login alone.

On the loopback door the owner check depends on `serve` setting the header. A
local process that connects to `127.0.0.1:8001` directly can forge it, but a
local process can already use `127.0.0.1:8000`, so this grants nothing new.

Moving the phone listener between the home-network address and the Tailscale
address changes its URL. After a move, the owner scans the token-free address QR
once, at the laptop; the pin and the bearer stay valid.
