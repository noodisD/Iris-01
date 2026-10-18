# queue.exhausted

**What it means:** A job failed every retry and stopped. Its `last_error` begins with the kind of failure.

**Confirm:** `SELECT source_type, source_id, left(last_error, 80) FROM processing_queue WHERE attempts >= 6` locally (the message may quote a source: read, do not paste).

**Safe fix:** Fix the cause, then re-queue once: `UPDATE processing_queue SET attempts = 0, next_attempt_at = NOW() WHERE id = …` (safe-auto).

**Never:** Do not re-queue the same failure in a loop: each attempt may cost a model call.

See [README](README.md) for action classes and the rules every check follows.
