# data.unread

**What it means:** Eligible entries are neither read nor queued, so patterns miss them.

**Confirm:** The check's evidence query lists their ids; the worker's ensure_pending normally re-queues them each pass.

**Safe fix:** If they stay unread across two runs, see queue.exhausted for why their reads fail.

**Never:** Do not insert accounts by hand.

See [README](README.md) for action classes and the rules every check follows.
