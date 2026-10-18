# data.reading_copies

**What it means:** A reading copy no longer has its entry's words; the reader would read words the owner did not write.

**Confirm:** The check lists ids.

**Safe fix:** `UPDATE reflections SET reading_copy = NULL WHERE id IN (…)` (safe-auto); the next read makes a new copy.

**Never:** Never keep a copy that fails same_words.

See [README](README.md) for action classes and the rules every check follows.
