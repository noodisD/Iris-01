# resources.backups

**What it means:** The newest backup is old, missing, or the backups take a lot of space.

**Confirm:** `ls -lt data/backups/`.

**Safe fix:** Take one: `uv run python scripts/backup_db.py manual` (safe-auto). List old ones for the owner to delete.

**Never:** Never delete backups without the owner's yes.

See [README](README.md) for action classes and the rules every check follows.
