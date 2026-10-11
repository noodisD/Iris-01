# Decisions

Each decision: what we chose, why, what else we could have done, and what each
option costs. Status is **made** (built or settled), **proposed** (my
recommendation, not yet built) or **open** (needs a choice before building).

---

## D1. Evaluate on a synthetic journal, not the real one — made

**Chosen:** an invented person's journal (`corpus_spec.md`), with patterns and
traps planted on purpose and the right answers recorded.

| Option | Pros | Cons |
|---|---|---|
| **Synthetic corpus** (chosen) | Can be public; every answer is known exactly; failures are planted, so each metric has something to catch | Cleaner than real life; may flatter or punish the system in ways real writing would not |
| Real journal | The true distribution of the owner's writing | Can never be published (privacy rule and scan); right answers would have to be labelled by hand, by the owner |
| Public dataset (e.g. a diary corpus) | Realistic, citable | No therapy sessions, no IRIS-style findings, no planted traps; licences vary |

**Interview line:** "I needed ground truth and a public repo, so I generated a
corpus with known answers and planted failure cases, and I say in the README
that synthetic data is cleaner than real writing."

---

## D2. Score today's chat before changing anything — made

**Chosen:** run the 30 questions against the unchanged chat and publish that as
the baseline.

| Option | Pros | Cons |
|---|---|---|
| **Baseline first** (chosen) | The only way to claim an improvement; can also show the change did not help | Costs a run (cents) and a day before building |
| Build first, evaluate after | Faster to a demo | No comparison: "it works" is not a result |

**Interview line:** "Baseline versus new is the whole story. If the new version
had not beaten it, I would have published that too."

---

## D3. Deterministic checks where possible, a model judge only where needed — made

**Chosen:** quotes, attribution, pattern names, firewall wording and retrieval
recall are checked by code; grounding and refusal by an LLM judge.

| Option | Pros | Cons |
|---|---|---|
| **Hybrid** (chosen) | Code checks are exact, free, repeatable and run in CI; the judge covers what code cannot | Two systems to explain; the judge still needs calibrating |
| LLM judge for everything | One mechanism; flexible | Non-deterministic, costs per run, can be wrong in the same way as the model it judges |
| Code only | Fully reproducible | Cannot tell a made-up claim that has no quote from a supported one |

**Why it fits IRIS:** IRIS already verifies quotes by code everywhere except
chat (`readable.locate`, `sessions.owner_turn`). The eval reuses those
functions, so the guardrail and the metric are the same code.

---

## D4. Calibrate the judge against the planted answers — made

**Chosen:** the judge's verdicts are compared with the expected behaviour of
each question (`expect:` in `questions.yaml`) and with the deterministic checks
where they overlap; agreement is reported.

| Option | Pros | Cons |
|---|---|---|
| **Against the corpus's known answers** (chosen) | No manual labelling; agreement is a number anyone can rerun | Only as good as the expected labels; covers behaviour, not nuance |
| Hand labels (~15 replies labelled by a person) | The standard practice; catches nuance | Manual work; one labeller's judgement |
| A stronger model as the reference | Cheap to scale | A model checking a model; shared blind spots |

**Rule:** a judge agreeing less than ~85% of the time is reported but not used
for headline numbers.

---

## D5. Thirty questions in six categories — made

**Chosen:** 5 questions each for recall, quotes, attribution, patterns,
absence (refusal) and firewall.

| Option | Pros | Cons |
|---|---|---|
| **30 targeted questions** (chosen) | Every failure mode is covered; small enough to run for cents and inspect by eye | Too few for tight statistics; one question moves a category by 20% |
| 100+ generated questions | Narrower error bars | Generated questions repeat themselves; expensive to check; harder to explain |

**Honest limit for the README:** with 5 per category, report counts ("0 of 5
leaked"), not decimals.

---

## D6. Recall@k is measured on its own — made

**Chosen:** for each question, check whether the gold entries were among the
k passages retrieved, before looking at the reply.

| Option | Pros | Cons |
|---|---|---|
| **Separate retrieval metric** (chosen) | Tells retrieval failures from generation failures, so you know what to fix | One more metric to explain |
| Only score the final answer | Simpler | A wrong answer could be either cause; you cannot tell which |

---

## D7. A LangGraph pipeline for chat — proposed

**Proposed:** retrieve → answer → grounding check → (one stricter retry) →
refuse, as a LangGraph state graph.

| Option | Pros | Cons |
|---|---|---|
| **LangGraph** (proposed) | Explicit, inspectable control flow with branches, retries and interrupts; widely asked for in job postings | A dependency and its abstractions for a flow that is small |
| Plain Python functions | No dependency; easy to read | Retries, branching and pausing for approval have to be hand-built |
| LangChain agent with tools | Fast to prototype | The model decides the flow, which is the opposite of what a guardrail needs |

**Why it is not just CV-driven:** the graph earns its place through the retry
branch and the human-in-the-loop interrupt (D10), not through the happy path.

---

## D8. What happens when a reply fails the check — open

| Option | Pros | Cons |
|---|---|---|
| **Hold, check, then stream** | Nothing unchecked is ever shown; simplest to reason about | Adds roughly 1-3 s before the first word; Talk mode waits longer |
| Stream, then retract and replace | Feels as fast as today | The owner may read a wrong claim before it is withdrawn |
| Stream with inline markers on unverified quotes | Fast and honest | More UI; does not stop invented claims without quotes |

**My recommendation:** hold-and-check. IRIS's whole stance is that nothing
unverified is presented as the owner's words; a short wait is worth it.

---

## D9. The grounding check is code first, model second — proposed

**Proposed:** the guardrail node first runs the deterministic checks (every
quote found word for word, owner turns only, named patterns among the admitted
findings, firewall wording). Only if those pass does an optional cheap model
check look for unsupported claims without quotes.

| Option | Pros | Cons |
|---|---|---|
| **Code, then optional model** (proposed) | Fast, free, and exact for the most damaging failures | The model step adds latency and cost when enabled |
| Model check only | Catches more kinds of error | Slower, costs every turn, can itself be wrong |
| Code check only | Free and exact | Misses invented claims that contain no quote |

---

## D10. The checkpointer pauses for the owner's approval — proposed

**Proposed:** a Postgres checkpointer lets the graph pause when chat proposes
an action that sends something to a model or costs money (adding a session,
reading what's new), show the cost, and resume on the owner's click.

| Option | Pros | Cons |
|---|---|---|
| **Checkpointer for human-in-the-loop** (proposed) | Matches IRIS's core rule (nothing sent without a click, cost first); a real use of interrupts | New tables and a migration |
| Checkpointer for chat history | What tutorials show | IRIS already stores conversations; duplicate state |
| No checkpointer | Simplest | No way to pause a graph mid-run for approval |

---

## D11. Tracing: export what IRIS already records — proposed

**Proposed:** IRIS already traces every model call with OpenTelemetry
(`obs_spans`, the Observatory). Export those traces to Langfuse only if a named
tool is wanted; otherwise report from IRIS's own traces.

| Option | Pros | Cons |
|---|---|---|
| **Reuse IRIS's OpenTelemetry, optional export** (proposed) | No second instrumentation; costs and latencies already recorded | "Langfuse" appears on the CV only if the export is set up |
| Self-hosted Langfuse | A named, popular tool; nice dataset-experiment UI | Needs ClickHouse, Redis and object storage; heavy for a laptop |
| No external tool | Nothing to run | Less to show visually |

---

## D12. Where each check runs — proposed

**Proposed:** deterministic tests run in CI on every push; the model-dependent
eval runs by hand (it costs money and varies run to run) and saves a scorecard
file that the README reads.

| Option | Pros | Cons |
|---|---|---|
| **Split: CI deterministic, manual model eval** (proposed) | CI stays free and stable; numbers in the README are reproducible from a saved file | The model eval can go stale if nobody reruns it |
| Everything in CI | Always current | Costs on every push; flaky failures from model variance |
| Everything manual | No CI setup | Regressions in the deterministic checks go unnoticed |
