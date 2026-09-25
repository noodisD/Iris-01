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

from . import decisions, discovery
from .database import db
from .ideas.service import IdeaService
from .library import load as load_library

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
               "depends_on": "depends on", "same_meaning": "means the same as"}


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
    rows = [d for d in discovery.differences(user_id, load_library())
            if (d["verdict"] or {}).get("verdict") == "rings_true"][:MAX_INSIGHTS]
    lines = ["## Differences in outcome they said ring true (differences, never causes)"]
    if not rows:
        lines.append("None yet.")
    for d in rows:
        lines.append(f"- When \"{d['patternName']}\" came up, \"{d['otherName']}\" was there {d['worse']} of "
                     f"{d['worseTotal']} times it went worse and {d['better']} of {d['betterTotal']} times it went better.")
    return lines


def _patterns(user_id: int) -> list[str]:
    rows = [s for s in discovery.summaries(user_id, load_library())
            if (s["verdict"] or {}).get("verdict") == "rings_true"][:MAX_PATTERNS]
    lines = ["## Patterns they said ring true (from a general library, found in their writing)"]
    if not rows:
        lines.append("None yet.")
    for s in rows:
        t = s["tones"]
        lines.append(f"- {s['pattern'].name}: {_cut(s['pattern'].statement, 200)} "
                     f"({s['occasions']} occasions: {t['worse']} went worse, {t['better']} better)")
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
    ("decisions", _decisions), ("sensors", _sensors), ("noticed", _noticed),
]


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
