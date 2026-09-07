# ADR-0011: Writing is separated from analysing, through a durable queue

## Status
Accepted — 2026-09-07

## Context
Embedding ran inside the request that stored the entry, and its failure was
caught and logged. An entry written while the embedding provider was down was
therefore stored and never became evidence: visible in the journal, invisible to
every analytical engine, with nothing to say the two disagreed and nothing that
would ever go back for it. The loss was silent, permanent, and indistinguishable
from having written nothing.

`run_processing_pipeline` also swallowed its own exception — the `raise` was
present but commented out — so even a caller that wanted to react could not.

The synchronous call also put an OpenAI round-trip on the path where the user is
waiting, for work whose result they do not see in that response.

## Decision
A write stores the row, enqueues it in `processing_queue`, and returns. A
background worker runs the pipeline: started by the API's lifespan and by the
CLI, so both surfaces process their own writes.

A queue row means "not yet processed". Success deletes it. Failure records the
error and schedules a retry on a widening backoff (1m, 5m, 15m, 1h, 6h, 24h).
Once the schedule is exhausted the row stays, holding its last error: an item
that is stuck and visible is better than one that has been quietly dropped.

`run_processing_pipeline` now re-raises. That is what makes the rest work — the
queue uses the exception to decide whether to retry, and a swallowed failure
would report success for work that had not happened, so the queue would delete
the item and turn a recoverable outage back into permanent loss.

## Consequences
Nothing written is lost to a provider outage, and the write path no longer waits
on a network round-trip: a journal POST returns in tens of milliseconds instead
of hundreds.

Analysis is now eventually consistent. Code that writes an entry and immediately
reads what was derived from it will see nothing yet — correct, and the reason
tests take an explicit `process_queue` fixture rather than an autouse one. A
test that hid the decoupling would stop testing it.

A queue that nothing drains is a slower way to lose the work, so any new entry
point that writes must start the worker or drain explicitly.
