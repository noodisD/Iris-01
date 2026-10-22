# money.spend

**What it means:** Model spend passed the daily budget (DAILY_BUDGET_USD), today or on average this week.

**Confirm:** `details.week_by_purpose` shows which purpose spent it; the Observatory's LLM view has the calls.

**Safe fix:** A retried pattern update: see queue.wasted. A run the owner started: nothing to do. Raise the budget in .env only with the owner.

**Never:** Never cut spend by switching models without the owner: a model change invalidates readings.

See [README](README.md) for action classes and the rules every check follows.
