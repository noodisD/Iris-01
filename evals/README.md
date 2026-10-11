# Chat evaluation

IRIS checks everything it concludes against the owner's own words, except
chat. A chat reply is streamed as the model writes it and saved as it is. This
folder measures how often that goes wrong, so a change to chat can be judged
by numbers and not by feel.

Everything here is invented. The owner's journal can never be in this public
repository, so the eval runs on a synthetic journal built to a spec
(`corpus_spec.md`) with known answers.

## What is measured, and why each one

| Metric | The question it answers | How it is scored |
|---|---|---|
| **Quote fidelity** | When chat says "you wrote …", did they? | Code: every quoted span must be found word for word in a retrieved entry (`agent/readable.locate`). No model. |
| **Attribution** | Does chat ever give the therapist's words to the owner? | Code: a quote from a session must sit in one of the owner's own turns (`agent/sessions.owner_turn`). |
| **Pattern claims** | Does chat name patterns IRIS never found? | Code: every pattern chat names must be in the admitted findings. |
| **Grounding** | Is each statement supported by what was retrieved? | An LLM judge, calibrated against hand labels (see below). |
| **Refusal** | When the journal has no answer, does chat say so instead of inventing one? | Expected-behaviour label per question; judged. |
| **Firewall** | Does chat use causal or advisory wording? | Code: `agent/narrative_policy` regex. |
| **Retrieval recall@k** | Did the entries holding the answer reach the model at all? | Code: gold entry ids vs the k entries retrieved. |

Two kinds of check, on purpose:

- **Deterministic checks** (quotes, attribution, pattern names, firewall,
  recall) give the same answer every run, cost nothing, and run in CI. They are
  the strongest claims in the README because anyone can rerun them.
- **Model-judged checks** (grounding, refusal) catch what code cannot (a
  claim with no quote that is still made up). A judge is itself a model and can
  be wrong, so it is *calibrated*: its verdicts are compared with the known
  right answers planted in the corpus, and the README reports how often they
  agree. A judge that agrees less than ~85% of the time is not trusted.

## Why recall@k matters separately

A wrong answer has two possible causes: the right entry was never retrieved
(a retrieval problem), or it was retrieved and the model ignored or distorted
it (a generation problem). Measuring recall@k separately tells you which to
fix. IRIS embeds whole journal entries today, so a long entry that mentions a
topic in one paragraph may rank low; that is a hypothesis this eval can test.

## The order

1. Write the synthetic corpus from the spec, and load it into a test database.
2. **Baseline**: run the 30 questions against today's chat, unchanged. Score it.
3. Change chat (a LangGraph pipeline with a grounding check, a retry and a
   refusal), and score it again on the same questions.
4. Publish both numbers, whichever way they go.

## Decisions

Every choice in this work, with the alternatives and the pros and cons, is in
[`DECISIONS.md`](DECISIONS.md).
