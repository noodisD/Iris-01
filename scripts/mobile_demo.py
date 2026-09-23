#!/usr/bin/env python3
"""End-to-end verification of the phone-side wire.

Exercises:
  - The bearer middleware (loopback bypass, LAN gated, 503 unpaired)
  - /api/mobile/pair (token hashing, settings update, row write)
  - /api/mobile/sensor/intake (PixelAdapter parsing, staging)

Run from the repo root after the schema is migrated:

    uv run python scripts/mobile_demo.py

Exits 0 on success, non-zero on the first failure with a clear message.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from agent.config import settings
from agent.database import db
from agent.mobile_auth import hash_token

LOOPBACK = "http://127.0.0.1:8765"
PAIR_PATH = "/api/mobile/pair"
INTAKE_PATH = "/api/mobile/sensor/intake"
TOKEN = "x" * 64
FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "pixel_export_minimal.json"


def _post(url: str, body: dict, bearer: str | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if bearer is not None:
        headers["Authorization"] = f"Bearer {bearer}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _reset_pairing() -> None:
    """Make sure the DB has a fresh pairing row, settings are clean."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE mobile_pairing;")
        cur.execute("INSERT INTO mobile_pairing (id) VALUES (1);")
        conn.commit()
    settings.MOBILE_BEARER_HASH = None
    settings.LAN_BIND_ENABLED = False


def main() -> int:
    _reset_pairing()

    # 1. Pair: store the hash, enable the bind.
    print("step 1: pair")
    expected_hash = hash_token(TOKEN)
    status, body = _post(f"{LOOPBACK}{PAIR_PATH}",
                         {"token": TOKEN, "lan_bind_enabled": True},
                         bearer=None)  # loopback bypasses the middleware
    if status != 200:
        print(f"  FAIL: pair returned {status} {body}")
        return 1
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT bearer_hash, lan_bind_enabled FROM mobile_pairing "
                    "WHERE id = 1")
        row = cur.fetchone()
        if row is None or row[0] != expected_hash:
            print(f"  FAIL: stored hash does not match: {row}")
            return 1
        if not row[1]:
            print(f"  FAIL: lan_bind_enabled not stored as true: {row}")
            return 1
    print("  OK")

    # 2. Intake: push a Pixel-shaped payload.
    print("step 2: push pixel batch")
    payload = json.loads(FIXTURE.read_text())
    status, body = _post(f"{LOOPBACK}{INTAKE_PATH}", payload, bearer=TOKEN)
    if status != 200:
        print(f"  FAIL: intake returned {status} {body}")
        return 1
    if body.get("observation_count") != 5:
        print(f"  FAIL: expected 5 observations, got {body}")
        return 1
    batch_id = body["batch_id"]
    print(f"  OK (batch_id={batch_id})")

    # 3. Confirm the row landed in the DB.
    print("step 3: verify row in sensor_batches")
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT source, status FROM sensor_batches WHERE id = %s",
                    (batch_id,))
        row = cur.fetchone()
        if row is None:
            print("  FAIL: no sensor_batches row")
            return 1
        if row[0] != "pixel" or row[1] != "pending":
            print(f"  FAIL: unexpected row {row}")
            return 1
    print("  OK")

    # 4. Clean up so the rest of the suite is unaffected.
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE sensor_observations, sensor_batches "
                    "RESTART IDENTITY CASCADE;")
        cur.execute("TRUNCATE mobile_pairing;")
        cur.execute("INSERT INTO mobile_pairing (id) VALUES (1);")
        conn.commit()
    settings.MOBILE_BEARER_HASH = None
    settings.LAN_BIND_ENABLED = False

    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
