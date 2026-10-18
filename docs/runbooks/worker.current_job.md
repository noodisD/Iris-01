# worker.current_job

**What it means:** One job has run longer than its usual limit.

**Confirm:** Watch `obs_spans` where `name = 'llm.chat'` for new calls in the last 10 minutes: calls arriving means it is slow, not stuck.

**Safe fix:** Slow on Flex: wait. Stuck (no calls for 30 min): restart (guarded) only if `--can-restart` agrees or the job's result is already out of date.

**Never:** Never restart in the middle of a `personal_dynamics` job just to deploy.

See [README](README.md) for action classes and the rules every check follows.
