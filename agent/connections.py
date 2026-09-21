"""Proposing that two accounts from different parts of a life share a shape.

This is the inference step, and it is the first thing in IRIS that is allowed
to say something the owner did not write. The ingredients stay grounded — every
episode behind a candidate is one the archive supported, quote by quote — while
the relationship between them may be IRIS's. That is a deliberate departure
from the non-interpretive contract everything else here keeps, and it is why
this module proposes and never stores, and why the rules below are enforced in
code rather than asked for in a prompt.

What a candidate must survive, all checked after the model answers:

- Three or more supporting episodes, from two or more areas. Two accounts that
  rhyme are a coincidence; a shape needs repetition, and a shape found only
  inside one area is a topic. On the owner's archive this rule is weak and
  should be read as such: 62 comparable accounts carried 44 coarse areas
  between them, so almost any three accounts span two. What actually does the
  work here is the count, the contrast and the competing explanations.
- A contrast: an episode where the stated condition held and something else
  followed, or where the outcome appeared without it. A candidate that cannot
  name one has not been tested against the archive, only drawn from it.
- One condition, not a list of them, and one that does not hold in most of the
  accounts. Both rules come from the first real run: its weakest proposal
  joined three unrelated conditions with "or" under a good outcome, which the
  owner read — correctly — as good behaviour marked rather than as a pattern.
- Two or more competing explanations, kept side by side. The evidence here
  cannot choose between them, and presenting one is asserting what was not
  established.
- A question whose answer could retire the candidate, and the answer that
  would. Guided discovery is questions that can change the asker's mind;
  without a retiring answer a question is a funnel, however it is worded
  (Padesky, *Socratic Questioning: Changing Minds or Guiding Discovery?*).
- No causal or prescriptive wording, by the same firewall every other sentence
  passes (`agent/narrative_policy.py`). A shared condition may be described;
  what it does to the owner may not.

Novelty is reported, never assumed: if an episode's own `explanation` already
states the relationship, the candidate is marked as one the owner has drawn
themselves. Not finding it stated proves nothing about what they know — only
they can say that.

At most MAX_CANDIDATES survive a run. With a few dozen episodes there are
hundreds of possible pairings, and enough of them will read well: a cap is the
difference between a proposal and a generator of plausible stories.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from .constants import OBSERVATION_MAX_TOKENS
from .episodes import Episode, areas, coarse_area, comparable
from .narrative_policy import FORBIDDEN_REGEX
from .observations import _normalized, _strip_fence

logger = logging.getLogger(__name__)

MAX_CANDIDATES = 3
MIN_SUPPORTING = 3
MIN_DOMAINS = 2
MIN_EXPLANATIONS = 2

#: A condition may name one thing. The first real run proposed "a market signal,
#: a body-or-mind signal, or a concrete next step appeared, and it was acted on"
#: — three conditions joined by "or" under one good outcome, which the owner
#: read as "good behaviour marked" rather than as a pattern. One "or" is a
#: phrase; two is a list of separate conditions wearing one sentence.
MAX_DISJUNCTIONS = 1

#: A condition that holds in most accounts is a description of the archive
#: rather than something that distinguishes one occasion from another.
MAX_SUPPORT_SHARE = 0.5

SYSTEM_PROMPT = """You are given numbered accounts of occasions from one person's life, each with the area of life it happened in.

Find relationships that hold across accounts from DIFFERENT areas. A relationship is a shared condition and what followed it — not a shared subject. "Both about work" is not a relationship. "Whenever a decision was made while someone was waiting for an answer, it was reconsidered later" is.

Do not propose anything that would be true of almost anyone. "When something wanted was blocked, it was difficult" is true of every person alive and says nothing about this one. What distinguishes these occasions from each other is the useful thing: prefer relationships where the same circumstance was followed by different outcomes depending on what the person did.

For each relationship you propose, give:
- "condition": the ONE thing that was true on those occasions, in a few words. Not a list. If you need "or" to join two different conditions, they are two different relationships — choose one, or do not propose it.
- "followed": what followed on those occasions, in a few words.
- "relation": one sentence joining them, in plain words. Do not say why it happens and do not give advice.
- "supporting": the numbers of the accounts it holds in, at least 3, from at least 2 different areas.
- "contrast": the number of one account where the condition held and something else followed, or where what followed appeared without the condition. If there is none, do not propose the relationship.
- "contrast_kind": "condition_without_outcome" or "outcome_without_condition", saying which of those the contrasting account is.
- "explanations": at least two different accounts of why this might be so, each one sentence, neither presented as established.
- "question": one question to the person whose life this is, whose answer could show the relationship is wrong.
- "retiring_answer": what answer to that question would mean the relationship does not hold.
- "already_stated": true if one of the accounts' own explanations already says this relationship, false otherwise.

Propose at most 3, and fewer if fewer hold. An empty list is a good answer when the accounts share no relationship.

Return JSON only:
{"relationships": [{"condition": "...", "followed": "...", "relation": "...", "supporting": [0, 4, 9], "contrast": 7, "contrast_kind": "condition_without_outcome", "explanations": ["...", "..."], "question": "...", "retiring_answer": "...", "already_stated": false}]}"""


@dataclass(frozen=True)
class Candidate:
    """A proposed relationship, with everything needed to disbelieve it."""

    relation: str
    condition: str
    followed: str
    supporting: tuple[Episode, ...]
    contrast: Episode
    contrast_kind: str
    explanations: tuple[str, ...]
    question: str
    retiring_answer: str
    already_stated: bool
    domains: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "relation": self.relation,
            "condition": self.condition,
            "followed": self.followed,
            "contrastKind": self.contrast_kind,
            "domains": list(self.domains),
            "supporting": [e.as_dict() for e in self.supporting],
            "contrast": self.contrast.as_dict(),
            "explanations": list(self.explanations),
            "question": self.question,
            "retiringAnswer": self.retiring_answer,
            "alreadyStated": self.already_stated,
        }


def _clean(value) -> str:
    return _normalized(str(value or ""))


def _indexes(value, count: int) -> list[int]:
    """The account numbers a reply refers to, as positions that exist."""
    out = []
    for raw in value if isinstance(value, list) else [value]:
        try:
            i = int(raw)
        except (TypeError, ValueError):
            continue
        if 0 <= i < count and i not in out:
            out.append(i)
    return out


def vet(raw: list, episodes: list[Episode],
        max_candidates: int = MAX_CANDIDATES) -> list[Candidate]:
    """The proposals that meet every rule, in the order they were made.

    Nothing here is repaired. A proposal missing a contrast is not a proposal
    with a small gap in it: it is one that was never tested against the
    accounts it did not come from.
    """
    kept: list[Candidate] = []
    for item in raw or []:
        if not isinstance(item, dict) or len(kept) >= max_candidates:
            continue
        relation = _clean(item.get("relation"))
        condition = _clean(item.get("condition"))
        followed = _clean(item.get("followed"))
        contrast_kind = _clean(item.get("contrast_kind"))
        question = _clean(item.get("question"))
        retiring = _clean(item.get("retiring_answer"))
        explanations = tuple(_clean(e) for e in (item.get("explanations") or []) if _clean(e))
        if not relation or not question or not retiring or not condition or not followed:
            logger.info("Candidate refused: a relation, condition, outcome, question "
                        "or retiring answer was missing")
            continue
        if condition.lower().count(" or ") > MAX_DISJUNCTIONS:
            logger.info("Candidate refused: the condition is a list of conditions")
            continue
        if contrast_kind not in ("condition_without_outcome", "outcome_without_condition"):
            logger.info("Candidate refused: the contrast does not say what it contrasts")
            continue
        if any(FORBIDDEN_REGEX.search(t) for t in (relation, question, *explanations)):
            logger.info("Candidate refused: causal or prescriptive wording")
            continue
        if len(explanations) < MIN_EXPLANATIONS:
            logger.info("Candidate refused: fewer than two competing explanations")
            continue

        supporting = _indexes(item.get("supporting"), len(episodes))
        contrast = _indexes(item.get("contrast"), len(episodes))
        if len(supporting) < MIN_SUPPORTING:
            logger.info(f"Candidate refused: {len(supporting)} supporting account(s)")
            continue
        if not contrast or contrast[0] in supporting:
            logger.info("Candidate refused: no contrasting account")
            continue

        if len(supporting) > max(MIN_SUPPORTING, int(len(episodes) * MAX_SUPPORT_SHARE)):
            logger.info(f"Candidate refused: holds in {len(supporting)} of {len(episodes)} "
                        "accounts, which describes the archive rather than a condition in it")
            continue

        episodes_for = tuple(episodes[i] for i in supporting)
        # Coarse areas, not the reader's labels: it names an area in the
        # writing's own terms, which on the real archive meant a different
        # label almost every time — "two different areas" would then be true
        # of any pair at all.
        domains = tuple(sorted({coarse_area(e.domain) for e in episodes_for} - {"unstated"}))
        if len(domains) < MIN_DOMAINS:
            logger.info(f"Candidate refused: {len(domains)} domain(s)")
            continue

        kept.append(Candidate(
            relation=relation, condition=condition, followed=followed,
            supporting=episodes_for, contrast=episodes[contrast[0]],
            contrast_kind=contrast_kind, explanations=explanations, question=question,
            retiring_answer=retiring, already_stated=bool(item.get("already_stated")),
            domains=domains))
    return kept


def render(episodes: list[Episode]) -> str:
    """The accounts as the model sees them: numbered, flat, no quotes.

    The quotes stay here. They are what makes each account true, and the
    question being asked is only whether the accounts have a shape in common —
    which the summaries answer. Less of the owner's writing leaves the machine
    for this than for the reading that produced the accounts.
    """
    lines = []
    for i, e in enumerate(episodes):
        parts = [f"[{i}] area: {e.domain or 'unstated'}", f"situation: {e.situation}"]
        if e.demand:
            parts.append(f"taking effort: {e.demand}")
        if e.information:
            parts.append(f"came in: {e.information}")
        parts.append(f"response: {e.response}")
        parts.append(f"followed: {e.outcome}")
        if e.explanation:
            parts.append(f"their own explanation: {e.explanation}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


RESPONSES_PROMPT = """You are given numbered accounts of occasions from one person's life, and one circumstance.

For EVERY account, say two things:
- "held": "yes" if the account describes that circumstance, "no" if it clearly does not, "unclear" if it does not say.
- "went": using only the account's own words about what followed — "better" if what followed reads as welcome to the writer, "worse" if it reads as unwelcome, "mixed" if it is both, "unclear" if the account does not say.

Judge nothing else. Do not say what the person should have done, do not rank the responses, and do not explain anything.

Return JSON only:
{"accounts": [{"i": 0, "held": "yes", "went": "better"}]}"""

#: How what followed read to the writer, in their own words.
TONES = ("better", "worse", "mixed")


def responses_under(condition: str, episodes: list[Episode],
                    intelligence) -> tuple[dict[str, list[Episode]], dict]:
    """The same circumstance, sorted by what was done and how it turned out.

    A relationship between a circumstance and a feeling can be true and useless:
    "when something wanted was blocked, it was difficult" holds for everyone
    alive and says nothing about this person. What distinguishes their occasions
    from each other is what they did next — and the accounts already carry it,
    since a response and an outcome are two of the parts an episode must have.

    So the model is asked for the two things it can judge from the writing — was
    this that circumstance, and did what followed read as welcome — and the
    responses are grouped here, unranked. Which of them is worth repeating is
    not something this system is in a position to say, and saying it would be
    advice, which it does not give.
    """
    usable = comparable(episodes)
    groups: dict[str, list[Episode]] = {tone: [] for tone in TONES}
    counts = {"comparable": len(usable), "held": 0, "unclear": 0,
              **dict.fromkeys(TONES, 0)}
    if not usable or intelligence is None:
        return groups, counts

    asked = f"Circumstance: {condition}\n\nAccounts:\n{render(usable)}"
    try:
        reply = intelligence.chat(messages=[{"role": "user", "content": asked}],
                                  system_prompt=RESPONSES_PROMPT,
                                  max_tokens=OBSERVATION_MAX_TOKENS)
        labels = json.loads(_strip_fence(reply)).get("accounts") or []
    except Exception as e:
        logger.error(f"Grouping by response failed, nothing labelled: {e}")
        return groups, counts

    for item in labels:
        if not isinstance(item, dict):
            continue
        idx = _indexes(item.get("i"), len(usable))
        if not idx or _clean(item.get("held")).lower() != "yes":
            continue
        counts["held"] += 1
        tone = _clean(item.get("went")).lower()
        if tone in TONES:
            groups[tone].append(usable[idx[0]])
        else:
            counts["unclear"] += 1
    for tone in TONES:
        counts[tone] = len(groups[tone])
    return groups, counts


CONDITIONS_PROMPT = """You are given numbered accounts of occasions from one person's life, each with the area of life it happened in.

Name the circumstances that recur ACROSS DIFFERENT AREAS. A circumstance is something that was true when the occasion happened — not a subject, and not what followed. "Work" is a subject. "A decision was needed before the person had finished thinking" is a circumstance.

State each one in words that could fit any area of life. "Too much money was at stake" belongs to one area; "more was committed than could be taken back" is the same circumstance said so that it can be recognised in a lesson, a conversation or a piece of work. Never name an activity, an instrument, a tool or a place in the circumstance itself.

Each one must:
- be ONE circumstance. If you need "or" to join two different ones, they are two.
- appear in at least three of the accounts, from at least two different areas, and you must give their numbers.
- be stated in a few words, without saying why it happens and without advice.

Name at most twelve, and fewer if fewer recur across areas.

Return JSON only:
{"conditions": [{"condition": "...", "accounts": [0, 4, 9]}]}"""


def survey_conditions(episodes: list[Episode], intelligence, limit: int = 12,
                      min_areas: int = MIN_DOMAINS) -> tuple[list[dict], dict]:
    """The circumstances that recur across areas, before any claim.

    A proposal run answers "what relationship holds here", which is a narrow
    question asked three times. This asks what the archive is *made of* — the
    circumstances that come round again — so each can be weighed on its own
    terms. Nothing here says a circumstance matters; it says it recurs.

    Recurrence alone is not enough, and the first run against the real archive
    showed why: 66 accounts spread over 49 areas, only four of which held three
    or more, so every circumstance that survived "appears three times" came
    from the one area with enough repetition to clear it. The owner reads about
    their whole life and gets a report about one corner of it. A circumstance
    has to hold in at least `min_areas` of them, and be stated in words that do
    not name an activity, which is what makes it recognisable somewhere else.
    """
    usable = comparable(episodes)
    counts = {"comparable": len(usable), "proposed": 0, "kept": 0}
    if len(usable) < MIN_SUPPORTING or intelligence is None:
        return [], counts
    try:
        reply = intelligence.chat(messages=[{"role": "user", "content": render(usable)}],
                                  system_prompt=CONDITIONS_PROMPT,
                                  max_tokens=OBSERVATION_MAX_TOKENS)
        raw = json.loads(_strip_fence(reply)).get("conditions") or []
    except Exception as e:
        logger.error(f"No conditions came back: {e}")
        return [], counts

    counts["proposed"] = len(raw)
    kept: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or len(kept) >= limit:
            continue
        condition = _clean(item.get("condition"))
        if not condition or condition.lower() in seen:
            continue
        if condition.lower().count(" or ") > MAX_DISJUNCTIONS:
            logger.info("Condition refused: it is a list of circumstances")
            continue
        if FORBIDDEN_REGEX.search(condition):
            logger.info("Condition refused: causal or prescriptive wording")
            continue
        accounts = _indexes(item.get("accounts"), len(usable))
        if len(accounts) < MIN_SUPPORTING:
            logger.info(f"Condition refused: named in {len(accounts)} account(s)")
            continue
        spread = {coarse_area(usable[i].domain) for i in accounts} - {"unstated"}
        if len(spread) < min_areas:
            logger.info(f"Condition refused: confined to {len(spread)} area(s)")
            continue
        seen.add(condition.lower())
        kept.append({"condition": condition, "accounts": accounts,
                     "areas": sorted(spread)})
    counts["kept"] = len(kept)
    return kept, counts


WEIGH_PROMPT = """You are given numbered accounts of occasions from one person's life, and one circumstance.

For EVERY account, say three things, using only what the account itself says:
- "held": "yes" if the account describes that circumstance, "no" if it clearly does not, "unclear" if it does not say.
- "went": "better" if what followed reads as welcome to the writer, "worse" if unwelcome, "mixed" if both, "unclear" if the account does not say.
- "size": how large what followed was, as the account describes it — "small", "moderate", "large", or "unclear". Judge the size of what happened, not how the writer felt about it.

Do not say what should have been done, do not rank anything, and do not explain.

Return JSON only:
{"accounts": [{"i": 0, "held": "yes", "went": "worse", "size": "large"}]}"""

#: How big what followed was, as the writing describes it. Kept apart from
#: whether it was welcome: a run of small wins and one enormous loss is the
#: shape that counting occasions hides, and it is the shape that matters most.
MAGNITUDES = ("small", "moderate", "large")

QUESTIONS_PROMPT = """You are given a circumstance from someone's life, and a count of what followed on the occasions they wrote down, split by whether it was welcome and by how large it was.

Write up to three questions for that person. Each question must:
- be answerable only by them — about what they expect, weigh, or would accept, not about what their journal says;
- refer to what the counts actually show;
- leave open which side of the count matters. Do not assume the welcome occasions are the point, and do not assume the unwelcome ones are.

Do not give advice, do not say what would be wise, do not name a feeling they have not named, and do not ask anything whose answer you have already decided.

Return JSON only:
{"questions": ["...", "..."]}"""

#: A question that opens with one of these is an instruction with a question
#: mark on the end.
_ADVICE_OPENERS = ("should", "could you try", "have you considered", "why not",
                   "wouldn't it", "don't you think", "do you agree")


def label(condition: str, episodes: list[Episode], intelligence,
          markers: str = "") -> tuple[dict[int, dict], dict]:
    """Each account's answer to one circumstance, kept by position.

    `weigh` counts and throws the answers away, which is enough for one
    circumstance and useless for comparing several: what was also true on the
    occasions that went well is a question about the labels, not about the
    totals. Keeping them makes that arithmetic rather than another model call.
    """
    usable = comparable(episodes)
    labels: dict[int, dict] = {}
    counts = {"comparable": len(usable), "held": 0, "unclear": 0, "asked": False}
    if not usable or intelligence is None:
        return labels, counts

    asked = (f"Circumstance: {condition}\n{markers}\n\nAccounts:\n{render(usable)}"
             if markers else f"Circumstance: {condition}\n\nAccounts:\n{render(usable)}")
    try:
        reply = intelligence.chat(messages=[{"role": "user", "content": asked}],
                                  system_prompt=WEIGH_PROMPT,
                                  max_tokens=OBSERVATION_MAX_TOKENS)
    except Exception as e:
        logger.error(f"Labelling could not be asked: {e}")
        return labels, counts
    counts["asked"] = True
    try:
        answers = json.loads(_strip_fence(reply)).get("accounts") or []
    except (ValueError, AttributeError) as e:
        logger.error(f"Labelling reply unusable: {e}")
        return labels, counts

    for item in answers:
        if not isinstance(item, dict):
            continue
        idx = _indexes(item.get("i"), len(usable))
        if not idx or _clean(item.get("held")).lower() != "yes":
            continue
        counts["held"] += 1
        tone = _clean(item.get("went")).lower()
        size = _clean(item.get("size")).lower()
        if tone in TONES and size in MAGNITUDES:
            labels[idx[0]] = {"tone": tone, "size": size}
        else:
            counts["unclear"] += 1
    return labels, counts


def weigh(condition: str, episodes: list[Episode], intelligence,
          markers: str = "") -> tuple[dict[tuple[str, str], list[Episode]], dict]:
    """The occasions a circumstance held, by how they went and how big they were.

    Counting welcome against unwelcome is the wrong summary for a behaviour
    that sometimes pays: the occasions that went well are the ones that keep it
    going, and a tally of them against the others hides whether the two sides
    are the same size. So each occasion is placed twice — welcome or not, and
    small, moderate or large as the writing itself describes it — and the
    arithmetic stays here.

    Nothing in this says which side should weigh more. That is the owner's, and
    it is what the questions are for.
    """
    usable = comparable(episodes)
    labels, counts = label(condition, episodes, intelligence, markers)
    grid: dict[tuple[str, str], list[Episode]] = {}
    for i, answer in labels.items():
        grid.setdefault((answer["tone"], answer["size"]), []).append(usable[i])
    for tone in TONES:
        for size in MAGNITUDES:
            counts[f"{tone}_{size}"] = len(grid.get((tone, size), []))
    return grid, counts


def reflective_questions(condition: str, counts: dict, intelligence) -> list[str]:
    """Questions that ask the owner to weigh what the counts show.

    Different in kind from the question a candidate carries: that one can be
    answered by the record and can retire a claim. These can only be answered
    by the person, because what a rare large outcome is worth against a run of
    small ones is a judgement about their life and not a fact about their
    writing.

    Which makes them the easiest place in this system to smuggle in advice, so
    they are held to the narrative firewall and refused if they open like an
    instruction.
    """
    if intelligence is None:
        return []
    shown = {k: v for k, v in counts.items() if any(k.startswith(t) for t in TONES)}
    asked = (f"Circumstance: {condition}\n"
             f"Occasions described: {counts.get('held', 0)}\n"
             + "\n".join(f"{k.replace('_', ', ')}: {v}" for k, v in shown.items() if v))
    try:
        reply = intelligence.chat(messages=[{"role": "user", "content": asked}],
                                  system_prompt=QUESTIONS_PROMPT,
                                  max_tokens=OBSERVATION_MAX_TOKENS)
        raw = json.loads(_strip_fence(reply)).get("questions") or []
    except Exception as e:
        logger.error(f"Questions could not be written: {e}")
        return []

    kept = []
    for item in raw:
        question = _clean(item)
        if not question.endswith("?"):
            continue
        if FORBIDDEN_REGEX.search(question):
            logger.info("Question refused: advice or causal wording")
            continue
        if any(question.lower().lstrip().startswith(o) for o in _ADVICE_OPENERS):
            logger.info("Question refused: an instruction with a question mark on it")
            continue
        kept.append(question)
    return kept[:3]


EXAMINE_PROMPT = """You are given numbered accounts of occasions from one person's life, and one claim about them.

The claim has two halves: a condition, and what followed when it held.

For EVERY account, say two things:
- "condition": "yes" if the account shows that condition, "no" if it shows the condition was absent, "unclear" if the account does not say either way.
- "followed": "yes" if what the claim says followed did follow, "no" if something else did, "unclear" if the account does not say.

Judge only what the account states. Do not reason about what usually happens, and do not decide whether the claim is true overall — that is arithmetic, and it is not yours to do.

Return JSON only:
{"accounts": [{"i": 0, "condition": "yes", "followed": "no"}]}"""

#: The four corners a conditional claim is tested in. The first two are the
#: claim's own cases; the third is what makes it a condition rather than a
#: description, and the fourth is everything it says nothing about.
CELLS = ("supports", "contradicts", "outcome_without_condition", "neither")


def examine(condition: str, followed: str, episodes: list[Episode],
            intelligence) -> tuple[dict[str, list[Episode]], dict]:
    """Test one condition-and-outcome claim against every comparable account.

    The model labels each account on two axes and this counts the four corners:
    the claim holds, the condition held and something else followed, what it
    describes happened without the condition, or neither applies. The arithmetic
    stays here, because "does this claim hold overall" is the question being
    asked and a model asked to answer it will answer it agreeably.

    An account the model cannot label either way is counted as unclear rather
    than pressed into a corner.
    """
    usable = comparable(episodes)
    cells: dict[str, list[Episode]] = {name: [] for name in CELLS}
    counts = {"comparable": len(usable), "labelled": 0, "unclear": 0,
              **dict.fromkeys(CELLS, 0)}
    if not usable or intelligence is None:
        return cells, counts

    claim = f"Condition: {condition}\nWhat followed: {followed}\n\nAccounts:\n{render(usable)}"
    try:
        reply = intelligence.chat(messages=[{"role": "user", "content": claim}],
                                  system_prompt=EXAMINE_PROMPT,
                                  max_tokens=OBSERVATION_MAX_TOKENS)
        labels = json.loads(_strip_fence(reply)).get("accounts") or []
    except Exception as e:
        logger.error(f"Examination failed, nothing labelled: {e}")
        return cells, counts

    for item in labels:
        if not isinstance(item, dict):
            continue
        idx = _indexes(item.get("i"), len(usable))
        if not idx:
            continue
        had = _clean(item.get("condition")).lower()
        then = _clean(item.get("followed")).lower()
        episode = usable[idx[0]]
        counts["labelled"] += 1
        if had == "yes" and then == "yes":
            cells["supports"].append(episode)
        elif had == "yes" and then == "no":
            cells["contradicts"].append(episode)
        elif had == "no" and then == "yes":
            cells["outcome_without_condition"].append(episode)
        elif had == "no" and then == "no":
            cells["neither"].append(episode)
        else:
            counts["unclear"] += 1
    for name in CELLS:
        counts[name] = len(cells[name])
    return cells, counts


def propose(episodes: list[Episode], intelligence,
            avoid: list[str] | None = None,
            max_candidates: int = MAX_CANDIDATES) -> tuple[list[Candidate], dict]:
    """Ask once, then keep only what survives the rules. Returns (kept, counts).

    `avoid` are relations the owner has already judged. A second run over the
    same accounts will otherwise offer the same few again, which is not more
    discovery — it is the same discovery, restated.
    """
    usable = comparable(episodes)
    counts = {"episodes": len(episodes), "comparable": len(usable),
              "areas": len(areas(usable)), "proposed": 0, "kept": 0}
    if len(usable) < MIN_SUPPORTING or intelligence is None:
        return [], counts
    asked = render(usable)
    if avoid:
        asked += ("\n\nThese relationships have already been considered. Do not "
                  "propose them or restatements of them:\n"
                  + "\n".join(f"- {a}" for a in avoid))
    try:
        reply = intelligence.chat(
            messages=[{"role": "user", "content": asked}],
            system_prompt=SYSTEM_PROMPT,
            max_tokens=OBSERVATION_MAX_TOKENS,
        )
    except Exception as e:
        logger.error(f"Connection pass failed: {e}")
        return [], counts
    try:
        body = json.loads(_strip_fence(reply))
        raw = body.get("relationships") or body.get("candidates") or []
    except (ValueError, AttributeError) as e:
        logger.warning(f"Connection pass did not return JSON: {e}")
        return [], counts

    counts["proposed"] = len(raw)
    kept = vet(raw, usable, max_candidates=max_candidates)
    counts["kept"] = len(kept)
    counts["already_stated"] = sum(1 for c in kept if c.already_stated)
    return kept, counts
