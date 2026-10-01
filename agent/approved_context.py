"""What the owner has approved, as one block of the chat's context.

Chat was wired to the old analytical engine: recent entries, a similarity
search and the engines' findings. Everything the owner has since confirmed
themselves, ideas, links between them, insights and patterns they said ring
true, their decision journal and the phone readings they accepted, never
reached it. This block carries exactly that, and nothing still waiting for a
decision: a proposal in Review is not something the owner said.

Each part is capped so a large framework cannot crowd out the conversation,
and each part that fails is reported as unavailable rather than empty, so the
model never mistakes "could not load" for "there is none".
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from datetime import date, timedelta

from . import observability as obs
from . import day_differences, decisions, discovery
from .database import db
from .days.recompute import list_days
from .ideas.service import IdeaService

logger = logging.getLogger(__name__)

HEADER = "# What they have approved"
MAX_IDEAS = 40
MAX_LINKS = 40
MAX_INSIGHTS = 20
MAX_PATTERNS = 20
MAX_DECISIONS = 10
SENSOR_DAYS = 14
STATEMENT_CHARS = 300

_LINK_WORDS = {"supports": "supports", "contradicts": "contradicts", "refines": "refines",
               "depends_on": "depends on", "same_meaning": "means the same as",
               "applies": "is an application of"}


def _cut(text: str, n: int = STATEMENT_CHARS) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n - 1] + "…"


def _ideas(user_id: int) -> list[str]:
    framework = IdeaService(user_id).framework()
    ideas = sorted(framework["ideas"], key=lambda i: -i["citationCount"])[:MAX_IDEAS]
    lines = ["## Ideas they hold (accepted by them; position is theirs, now)"]
    if not ideas:
        lines.append("None accepted yet.")
    for i in ideas:
        span = " to ".join(sorted({d for d in (i["firstWrittenOn"], i["lastWrittenOn"]) if d}))
        written = f"written {i['citationCount']}x" + (f", {span}" if span else "")
        lines.append(f"- [{i['domain']}, {i['position']}] {_cut(i['statement'])} ({written})")
    links = framework["links"][:MAX_LINKS]
    if links:
        lines.append("Connections they accepted between those ideas:")
        for link in links:
            lines.append(f"- \"{_cut(link['fromStatement'], 120)}\" {_LINK_WORDS.get(link['kind'], link['kind'])} "
                         f"\"{_cut(link['toStatement'], 120)}\"")
    return lines



def _insights(user_id: int) -> list[str]:
    current, _ = discovery.insights(user_id, period="all")
    rows = [card for card in current if card.feedback is not None
            and card.feedback.verdict == "rings_true"
            and not card.feedback.needs_review][:MAX_INSIGHTS]
    lines = ["## Personal insights the owner accepted as possibilities (still tentative)"]
    if not rows:
        lines.append("None yet.")
    for card in rows:
        lines.append(
            f"- {_cut(card.title, 100)}: observed {_cut(card.observation.text, 180)} "
            f"Owner-endorsed possibility, not an established cause: "
            f"{_cut(card.possible_meaning.text, 180)} "
            f"Materially different rival: {_cut(card.alternative.text, 180)}")
    return lines


def _patterns(user_id: int) -> list[str]:
    current, _ = discovery.patterns(user_id, period="all")
    rows = [card for card in current if card.feedback is not None
            and card.feedback.verdict == "rings_true"
            and not card.feedback.needs_review][:MAX_PATTERNS]
    lines = ["## Personal dynamics the owner said ring true (observation only, not a motive)"]
    if not rows:
        lines.append("None yet.")
    for card in rows:
        lines.append(
            f"- {_cut(card.title, 100)}: when {_cut(card.context.text, 160)}, "
            f"{_cut(card.response.text, 160)} "
            f"[{card.evidence_state}; at least {card.independent_group_count} distinct events]. "
            "The owner approved this observation, not Iris's suggested explanation.")
    return lines


def _decisions(user_id: int) -> list[str]:
    rows = decisions.list_for(user_id, limit=MAX_DECISIONS)
    lines = [f"## Decisions they logged (newest {MAX_DECISIONS})"]
    if not rows:
        lines.append("None logged yet.")
    for d in rows:
        facts = [f"stake {d['stake']}" if d.get("stake") else "",
                 f"confidence {d['confidence']}%" if d.get("confidence") is not None else "",
                 f"feeling {d['feeling']}" if d.get("feeling") else "",
                 "pressures " + ", ".join(d["pressures"]) if d.get("pressures") else ""]
        line = f"- [{d['decided_on']}] {_cut(d['what'], 200)}"
        extra = "; ".join(f for f in facts if f)
        if extra:
            line += f" ({extra})"
        if d.get("outcome"):
            line += f". Outcome: {_cut(d['outcome'], 200)}"
            if d.get("followed_plan"):
                line += f"; followed plan: {d['followed_plan']}"
        lines.append(line)
    return lines


def _sensors(user_id: int) -> list[str]:
    """Accepted phone readings over the last fortnight, summarised per kind.

    Only batches the owner confirmed. Numbers are averaged per day; text
    readings name their most frequent values. Coordinates are never included.
    """
    since = date.today() - timedelta(days=SENSOR_DAYS)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT o.source_type, o.occurred_date, o.value_num, o.value_text
                 FROM sensor_observations o JOIN sensor_batches b ON b.id = o.batch_id
                WHERE b.status = 'confirmed' AND o.occurred_date >= %s""", (since,))
        rows = cur.fetchall()
    lines = [f"## Phone readings they accepted (last {SENSOR_DAYS} days)"]
    if not rows:
        lines.append("None accepted in this period.")
        return lines
    by_kind: dict[str, list[tuple]] = {}
    for kind, day, num, text in rows:
        by_kind.setdefault(kind, []).append((day, num, text))
    for kind, readings in sorted(by_kind.items()):
        days = {r[0] for r in readings}
        nums = [r[1] for r in readings if r[1] is not None]
        texts = Counter(r[2] for r in readings if r[2])
        part = f"- {kind}: {len(readings)} readings over {len(days)} days"
        if nums:
            part += f", average {sum(nums) / len(nums):.1f} per reading"
        if texts:
            part += ", most often " + ", ".join(f"{t} ({n})" for t, n in texts.most_common(3))
        lines.append(part)
    return lines

def _days(user_id: int) -> list[str]:
    """Only current qualifying comparisons with a saved owner opinion."""
    rows = [row for row in day_differences.for_user(user_id)
            if (row["verdict"] or {}).get("verdict") == "rings_true"][:MAX_INSIGHTS]
    lines = ["## Current day differences with an owner's saved rings-true opinion (observational, never causes)"]
    if not rows:
        lines.append("None yet.")
    for row in rows:
        lines.append(f"- Saved opinion; current {row['leftLabel']} averaged {row['leftMean']} "
                     f"across {row['leftCount']} days versus {row['rightMean']} across "
                     f"{row['rightCount']} {row['rightLabel']}. Not a cause or a rule.")
    return lines


CHECKIN_DAYS = 14


def _checkins(user_id: int) -> list[str]:
    """Their own daily check-ins, one line a day: numbers they gave, nothing inferred."""
    since = date.today() - timedelta(days=CHECKIN_DAYS)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT reflection_date, energy_level, metrics FROM reflections
                WHERE user_id = %s AND reflection_date >= %s
                  AND (energy_level IS NOT NULL OR metrics IS NOT NULL)
                ORDER BY reflection_date, id""", (user_id, since))
        scores = day_differences.scores_from_rows(cur.fetchall())
    lines = [f"## Their check-ins (last {CHECKIN_DAYS} days; 1-10, their own numbers)"]
    if not scores:
        lines.append("None recorded in this period.")
    for day in sorted(scores, reverse=True):
        values = ", ".join(f"{name.replace('_', ' ')} {value:g}" for name, value in scores[day].items())
        lines.append(f"- {day}: {values}")
    return lines


def _measured_days(user_id: int) -> list[str]:
    """Day summaries built from phone and Timeline readings they confirmed. No coordinates."""
    since = (date.today() - timedelta(days=CHECKIN_DAYS)).isoformat()
    rows = [row for row in list_days(user_id) if row["day"] >= since]
    lines = [f"## Their measured days (last {CHECKIN_DAYS} days, from readings they confirmed)"]
    if not rows:
        lines.append("None measured in this period.")
    for row in rows:
        facts = [f"{row['dayKind']} day" if row["dayKind"] != "unknown" else "place unknown"]
        if row["commuteMinutes"]:
            facts.append(f"commute {row['commuteMinutes']} min" + (f" by {row['commuteMode']}" if row["commuteMode"] else ""))
        if row["steps"] is not None:
            facts.append(f"{row['steps']} steps" + ("" if row["stepsFullDay"] else " (partial day)"))
        if row["screenMinutes"]:
            facts.append(f"screen {row['screenMinutes']} min")
        if row["sleepMinutes"]:
            facts.append(f"slept {row['sleepMinutes']} min")
        lines.append(f"- {row['day']}: " + ", ".join(facts))
    return lines


def _noticed(user_id: int) -> list[str]:
    confirmed = [t for t in db.get_themes(user_id) if t.get("origin") == "observed"]
    lines = ["## Patterns they confirmed under Noticed"]
    if not confirmed:
        lines.append("None confirmed yet.")
    for t in confirmed[:MAX_PATTERNS]:
        lines.append(f"- {_cut(t['summary'], 200)}")
    return lines


PARTS: list[tuple[str, Callable[[int], list[str]]]] = [
    ("ideas", _ideas), ("insights", _insights), ("patterns", _patterns),
    ("decisions", _decisions), ("checkins", _checkins), ("measured days", _measured_days),
    ("sensors", _sensors), ("days", _days), ("noticed", _noticed),
]


@obs.traced("chat.approved_context", "chat")
def approved_context(user_id: int) -> str:
    """The block, headed, with each part or a line saying it could not load."""
    out = [HEADER + ":"]
    for name, part in PARTS:
        try:
            out.extend(part(user_id))
        except Exception as exc:
            logger.error("approved context part %s failed (%s)", name, type(exc).__name__)
            out.append(f"## {name}: could not be loaded just now (not the same as none).")
    return "\n".join(out)
