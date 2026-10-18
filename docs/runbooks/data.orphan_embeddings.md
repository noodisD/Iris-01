# data.orphan_embeddings

**What it means:** Memory vectors point at deleted things; chat may recall nothing for them or fail.

**Confirm:** The evidence query counts them by kind.

**Safe fix:** Delete those embedding rows (safe-auto) and fix the delete path that left them.

**Never:** —

See [README](README.md) for action classes and the rules every check follows.
