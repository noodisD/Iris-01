# queue.wasted

**What it means:** Failed attempts threw away a lot of work this week, usually pattern updates failing hours in and starting again.

**Confirm:** `SELECT started_at, round(duration_ms/60000), attributes->>'iris.queue.outcome' FROM obs_spans WHERE name='queue.job' AND attributes->>'iris.queue.source_type'='personal_dynamics' ORDER BY 1`; errors.new_kinds names the failure.

**Safe fix:** If the cause is the Flex tier refusing calls (429), the fix is in code: retry those calls in place rather than failing the run (needs-owner).

**Never:** Never restart a running pattern update to try again sooner.

See [README](README.md) for action classes and the rules every check follows.
