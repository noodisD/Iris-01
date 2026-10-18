# data.passages

**What it means:** A session or long entry has no recall passages, so chat cannot find its parts.

**Confirm:** The check lists ids.

**Safe fix:** Re-run passage indexing for them: `pipeline._index_entry_passages` or re-queue the reflection job (safe-auto).

**Never:** —

See [README](README.md) for action classes and the rules every check follows.
