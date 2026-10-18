# worker.alive

**What it means:** The queue worker thread died; entries stop becoming evidence.

**Confirm:** `curl -s 127.0.0.1:8000/api/observatory/overview` → `probe.worker.alive`.

**Safe fix:** Restart (guarded). Then find the exception in the journal: the worker should survive any single pass.

**Never:** Do not run the queue by hand while the server's worker is alive: both would claim the same jobs.

See [README](README.md) for action classes and the rules every check follows.
