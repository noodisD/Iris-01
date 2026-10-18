# data.duplicates

**What it means:** The same text is stored more than once.

**Confirm:** `SELECT content_hash, array_agg(id) FROM reflections GROUP BY 1 HAVING count(*) > 1`.

**Safe fix:** Show the owner the ids; deleting is their decision (needs-owner).

**Never:** Never delete without the owner.

See [README](README.md) for action classes and the rules every check follows.
