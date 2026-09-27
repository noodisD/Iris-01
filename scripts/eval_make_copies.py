"""Make the two databases for the with-and-without-history test.

    uv run python scripts/eval_make_copies.py

Copies the live database into `iris_eval_full` and `iris_eval_direct`, then
takes the imported archive, and everything derived from it, out of the second
(see agent/eval_copies.py). The live database is only read. Running it again
replaces both copies with fresh ones, so the test can be repeated as more is
written directly.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent.config import settings
from agent.eval_copies import clear_queue, prune_to_direct

COPIES = ("iris_eval_full", "iris_eval_direct")


def _connect(dbname: str):
    return psycopg2.connect(dbname=dbname, user=settings.POSTGRES_USER, password=settings.POSTGRES_PASSWORD,
                            host=settings.POSTGRES_HOST, port=settings.POSTGRES_PORT)


def _pg(args: list[str]) -> None:
    env = {**os.environ, "PGPASSWORD": settings.POSTGRES_PASSWORD}
    base = ["-h", settings.POSTGRES_HOST, "-p", str(settings.POSTGRES_PORT), "-U", settings.POSTGRES_USER]
    subprocess.run([args[0], *base, *args[1:]], check=True, env=env)


def main() -> None:
    live = settings.POSTGRES_DB
    if live in COPIES:
        sys.exit("POSTGRES_DB points at an eval copy; point it at the live database to copy from.")
    Path(settings.DATA_DIR, "eval").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=Path(settings.DATA_DIR, "eval")) as tmp:
        dump = Path(tmp, "live.dump")
        print(f"Reading {live}…")
        _pg(["pg_dump", "-Fc", "-f", str(dump), live])
        admin = _connect("postgres")
        admin.autocommit = True
        for name in COPIES:
            with admin.cursor() as cur:
                cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
                cur.execute(f'CREATE DATABASE "{name}"')
            _pg(["pg_restore", "--no-owner", "-d", name, str(dump)])
        admin.close()

    with _connect("iris_eval_full") as conn, conn.cursor() as cur:
        print(f"iris_eval_full: everything; {clear_queue(cur)} queued jobs dropped.")
    with _connect("iris_eval_direct") as conn, conn.cursor() as cur:
        counts = prune_to_direct(cur)
        cur.execute("SELECT count(*) FROM reflections")
        entries = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM ideas WHERE status = 'active'")
        ideas = cur.fetchone()[0]
    removed = ", ".join(f"{v} {k}" for k, v in counts.items() if v)
    print(f"iris_eval_direct: {entries} entries and {ideas} accepted ideas left. Removed: {removed}.")


if __name__ == "__main__":
    main()
