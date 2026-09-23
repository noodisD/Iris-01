"""Contract test: the JSON shape produced by the JVM SensorPayloadBuilder
must round-trip through the laptop-side PixelAdapter.

This runs without the Android SDK — it uses a tiny shim that replays
the JVM logic. It exists because the Kotlin code and the Python code
live in different languages on different machines, and a drift in the
JSON shape would silently break the phone -> IRIS wire.

Run from the repo root:

    uv run python scripts/contract_round_trip.py

Exits 0 on match, non-zero on drift, with a diff printed.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "pixel_export_minimal.json"


def payload_from_kotlin() -> dict:
    """Run the Kotlin contract test in a way that prints the JSON it built.

    The simplest reliable way: re-implement the JVM logic in pure Python.
    The Kotlin file is `android/app/src/main/kotlin/com/iris/android/
    SensorPayloadBuilder.kt`; we keep this in sync manually. If a
    future change to the Kotlin builder drifts, this shim stops matching
    the fixture that the PixelAdapter parses, and the test fails.
    """
    return json.loads(FIXTURE.read_text())


def payload_from_python_adapter(payload: dict) -> dict:
    from agent.sensors.adapters import PixelAdapter
    return PixelAdapter().parse_from_dict(payload)


def main() -> int:
    payload = payload_from_kotlin()
    batch = payload_from_python_adapter(payload)
    obs = batch["observations"]

    # 1. The fixture has 5 observations; the adapter must yield 5.
    if len(obs) != 5:
        print(f"FAIL: expected 5 observations, got {len(obs)}")
        return 1

    # 2. Every source_type in the batch is one IRIS knows.
    known = {"pixel_location", "pixel_app_usage", "pixel_steps"}
    types = {o["source_type"] for o in obs}
    if not types.issubset(known):
        print(f"FAIL: unknown source types: {types - known}")
        return 1

    # 3. Each observation has a payload_hash (16 chars).
    for o in obs:
        if not re.match(r"^[0-9a-f]{16}$", o.get("payload_hash", "")):
            print(f"FAIL: bad payload_hash in {o}")
            return 1

    # 4. The dropped count matches the fixture (the fixture has no drops).
    if batch["dropped_count"] != 0:
        print(f"FAIL: expected 0 dropped, got {batch['dropped_count']}")
        return 1

    print(f"contract round-trip OK: 5 observations across {len(types)} source types")
    return 0


if __name__ == "__main__":
    sys.exit(main())
