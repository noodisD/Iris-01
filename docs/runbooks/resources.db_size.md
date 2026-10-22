# resources.db_size

**What it means:** The database is large or growing fast.

**Confirm:** `details.largest_tables_mb` names the tables; compare with the previous run's value.

**Safe fix:** Telemetry: see resources.telemetry. A cache: find its writer and add pruning.

**Never:** Never delete evidence tables to save space.

See [README](README.md) for action classes and the rules every check follows.
