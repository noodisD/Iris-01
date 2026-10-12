#!/usr/bin/env python3
"""Back up the live database before a migration or a data change.

    uv run python scripts/backup_db.py pre_0051          # data/backups/iris_db_pre_0051_<time>.dump

The Observatory's tables (obs_*) keep their structure but not their rows: they
are a week of the server describing itself, rebuilt as it runs, and were nine
tenths of every dump. Leaving them out makes a backup a tenth of the size.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from agent.config import settings

BACKUPS = Path(__file__).resolve().parent.parent / "data" / "backups"


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "manual"
    BACKUPS.mkdir(parents=True, exist_ok=True)
    out = BACKUPS / f"{settings.POSTGRES_DB}_{label}_{time.strftime('%Y%m%d_%H%M%S')}.dump"
    env = dict(os.environ, PGPASSWORD=settings.POSTGRES_PASSWORD)
    subprocess.run(["pg_dump", "-Fc", "-h", settings.POSTGRES_HOST, "-p", str(settings.POSTGRES_PORT),
                    "-U", settings.POSTGRES_USER, "--exclude-table-data=obs_*", "-f", str(out),
                    settings.POSTGRES_DB], check=True, env=env)
    print(f"{out} ({out.stat().st_size // 1_000_000} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
