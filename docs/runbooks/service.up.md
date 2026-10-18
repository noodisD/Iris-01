# service.up

**What it means:** IRIS does not answer on 127.0.0.1:8000.

**Confirm:** `systemctl --user status iris`; `journalctl --user -u iris -n 100`.

**Safe fix:** If it crashed on start, read the traceback; a failed migration stops start-up. Restart (guarded) once the cause is fixed.

**Never:** Do not edit an applied migration to get past an error: migrations are checksummed.

See [README](README.md) for action classes and the rules every check follows.
