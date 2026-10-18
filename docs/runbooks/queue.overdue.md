# queue.overdue

**What it means:** Jobs have waited over an hour to be taken.

**Confirm:** See worker.current_job: usually one long job holds the worker.

**Safe fix:** Wait for the long job; if the worker is dead see worker.alive.

**Never:** Do not start a second worker.

See [README](README.md) for action classes and the rules every check follows.
