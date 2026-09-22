"""Whether a field of an account is stated by the writing it cites.

The reader proves a quote appears in the entry it names. It never proved the
*account* follows from that quote, and a check of ten accounts found where that
gap lands: `outcome` wrong on five of the six checked accounts that enter
comparison, `response` wrong or partial on five of ten.

The mechanism is selection, not carelessness. `outcome` is the only part of the
frame ever absent — across 97 accounts, `situation` is missing 0 times,
`response` 0 times, `outcome` 26 — and `has_shape` requires it. So an account
earns its way into the comparison set by having an outcome, which makes
supplying one the way in. Omitting it honestly, as the prompt asks, is what
gets an account excluded.

This closes that by asking of a field what `check_support` asks of a claim: not
"is this plausible" but "does this passage say it". Four answers, and the
fourth matters as much as the others:

    supported     the quotes state it
    not_stated    the quotes do not say it, either way
    contradicted  the quotes say something else happened
    unavailable   the model could not be asked

`unavailable` is a provider failure, not a verdict. Collapsing it into
`not_stated` would turn an exhausted API key into "the journal records no
outcome", which is the same mistake this codebase has now made twice and is
the reason the reading copies and the pattern labels both count what they could
not ask separately from what came back empty.

Nothing here edits an account. A field that fails is recorded as failing; the
account stays whole and the analyses that need that field exclude it. Deciding
what an account says is the owner's, and a second model agreeing is a check,
not a proof.

This deliberately does not borrow `check_support`'s recurrence thresholds. Two
entries are required there because a *pattern* claimed across an archive needs
more than one occasion behind it. One occasion needs one occasion.

MEASURED, AND NOT YET FIT TO GATE ANYTHING
------------------------------------------
Run against the ten accounts the owner checked by hand (22 September 2026):

    response   10 supported, 0 not_stated, 0 contradicted
    outcome     5 supported, 2 not_stated, 0 contradicted

    agreed with the owner on 7 of 13 scorable verdicts (54%)
    caught 1 of the 6 errors they found
    rejected 1 field they had confirmed as right

Asked whether a passage says a thing, the model says yes. It reproduces the
extractor's own judgement rather than testing it, which is the failure the
design was warned about and did not avoid: a second model agreeing is not
evidence, and here it agrees almost always.

So this must not be used to admit or exclude an account. What it is good for is
the shape around it — stable keys, `unavailable` kept apart from `not_stated`,
results versioned beside an untouched cache. The judgement in the middle needs
replacing, not tuning. Two candidates, neither tried yet:

- make the model *select* rather than assess: ask which passage states the
  field, mechanically verify that the passage it names is real and contains
  what it claims, and treat "none" as not_stated. A citation that must be
  produced is harder to hand-wave than a yes.
- ask for a calibrated probability from a model built to return one, and put
  the threshold where the owner's own verdicts say it belongs.
"""

from __future__ import annotations

import hashlib
import json
import logging

from .constants import OBSERVATION_MAX_TOKENS
from .observations import _strip_fence

logger = logging.getLogger(__name__)

#: Bumped when the prompt or the verdicts change, so a stored result is never
#: read as though it came from a rule it did not.
VERIFICATION_VERSION = 1

#: The fields worth checking: the two the spot-check found unreliable. Both are
#: claims about what occurred, which is what a quote can settle.
CHECKED = ("response", "outcome")

VERDICTS = ("supported", "not_stated", "contradicted", "unavailable")

SYSTEM_PROMPT = """You are checking one statement about an occasion against the passages it was drawn from.

The passages are real: each was found word for word in the writing. You are not judging whether the statement is plausible, or whether it sounds like something that happens. You are judging whether these passages say it.

Answer for each statement given:
- "supported" — the passages state this, about this person, on this occasion.
- "not_stated" — the passages do not say it. They may be about the same occasion and simply not mention this.
- "contradicted" — the passages say something that cannot be true alongside it.

Two things make a statement NOT supported even when it seems right:
- it is about a different person than the one the passages describe;
- it is something intended, feared or imagined, reported as something that happened.

"not_stated" is the correct and expected answer when the writing simply does not say. It is not a failure to find something.

Do not restate the statement. Give only the verdict for each one.

Return JSON only, in exactly this form:
{"verdicts": [{"field": "<the field name you were given>", "verdict": "supported" | "not_stated" | "contradicted"}]}"""


def account_key(episode: dict) -> str:
    """A stable name for an account, independent of its place in a list.

    Positions move the moment anything is filtered, and a verdict that points
    at "account #61" is wrong as soon as an earlier account is dropped. This
    is derived from what the account is made of, so a result can be read back
    against a different cache and still name the same thing.
    """
    parts = [(episode.get("situation") or ""), (episode.get("response") or "")]
    parts += sorted(f"{c.get('sourceType', 'reflection')}:{c.get('entryId')}"
                    for c in episode.get("citations", []))
    return hashlib.sha1("\u0000".join(parts).encode()).hexdigest()[:12]


def _asked(episode: dict) -> tuple[str, dict[str, str]]:
    """What to send, and the fields it covers."""
    fields = {f: episode[f] for f in CHECKED if episode.get(f)}
    quotes = "\n".join(f"- {c.get('text')}" for c in episode.get("citations", []))
    said = (f"The passages, as the writing has them:\n{quotes}\n\n"
            f"The occasion is described as: {episode.get('modality')}, "
            f"by: {episode.get('actor')}.\n\n"
            "The statements to check:\n"
            + "\n".join(f"- {name}: {text}" for name, text in fields.items()))
    return said, fields


def check(episode: dict, intelligence) -> dict[str, str]:
    """A verdict per checked field. Never raises, never edits the account."""
    said, fields = _asked(episode)
    if not fields:
        return {}
    if intelligence is None:
        return dict.fromkeys(fields, "unavailable")
    try:
        reply = intelligence.chat(messages=[{"role": "user", "content": said}],
                                  system_prompt=SYSTEM_PROMPT,
                                  max_tokens=OBSERVATION_MAX_TOKENS)
    except Exception as e:
        logger.error(f"Field support could not be asked: {e}")
        return dict.fromkeys(fields, "unavailable")
    try:
        answer = json.loads(_strip_fence(reply))
    except (ValueError, AttributeError):
        # An unreadable answer is not a judgement about the field either.
        return dict.fromkeys(fields, "unavailable")
    # Keyed by field name rather than positionally, and read from an explicit
    # "verdicts" list: asking for {"response": ...} invited the model to put the
    # restated statement under that key, because "response" names a field here
    # and an answer everywhere else. Two accounts came back that way and were
    # counted as provider failures.
    given = {}
    for item in (answer.get("verdicts") or []):
        if isinstance(item, dict):
            given[item.get("field")] = item.get("verdict")
    return {name: (given.get(name) if given.get(name) in VERDICTS[:3] else "unavailable")
            for name in fields}


def tally(results: list[dict]) -> dict:
    """Counts by field and verdict, with what could not be asked kept apart."""
    counts: dict[str, dict[str, int]] = {f: dict.fromkeys(VERDICTS, 0) for f in CHECKED}
    for row in results:
        for field, verdict in (row.get("verdicts") or {}).items():
            if field in counts:
                counts[field][verdict] = counts[field].get(verdict, 0) + 1
    return counts
