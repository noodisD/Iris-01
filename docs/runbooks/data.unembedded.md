# data.unembedded

**What it means:** Processed entries without an embedding cannot be recalled in chat.

**Confirm:** The check's evidence query lists their ids.

**Safe fix:** Re-queue their 'reflection' processing jobs (safe-auto).

**Never:** Do not mark entries complete by hand.

See [README](README.md) for action classes and the rules every check follows.
