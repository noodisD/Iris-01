# owner.sessions

**What it means:** A therapy session is staged but not imported.

**Confirm:** `SELECT id, status, voices_status FROM session_imports WHERE status = 'staged'`.

**Safe fix:** Tell the owner; importing sends it to be read, so it is their click.

**Never:** Never import or run the voices pass on the owner's behalf.

See [README](README.md) for action classes and the rules every check follows.
