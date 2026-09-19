"""Patterns at the scale of a life, not a fortnight.

Every other engine looks through a window of 14 to 90 days. On an archive
spanning 27 months that is a keyhole: none of the owner's 19 themes had an
occurrence in the last 90 days, while 14 of them had three or more across the
whole record. Fourteen themes with something to say, and no engine able to
reach it — the evidence was never thin, the ruler was wrong.

This scale counts the same occurrences over the whole span. It adds no
evidence, calls no model, and creates nothing: it is the existing occurrences,
measured at a resolution that fits the writing.

What it reports is arithmetic, not judgement. How many times, between which
dates, across how many months, which year holds most of them, and how long
since the last. The single label distinguishes a pattern that ran throughout
from one that clustered in a stretch, by a stated threshold — nothing here
infers why, and nothing describes the person.

It never claims the present, which is what earns it the coverage gate's
exemption (`agent/coverage.py`). "Twelve times across two years, none since
March" is true whether or not this month is quiet; withholding it because
recent writing is thin would suppress the fact exactly when it is most worth
knowing. Anything claiming how things *are* stays gated.
"""

from __future__ import annotations

import logging
from collections import Counter

from .constants import (
    LIFELONG_CONCENTRATION_SHARE,
    LIFELONG_MIN_OCCURRENCES,
    LIFELONG_MIN_SPAN_DAYS,
)
from .database import themes
from .timeutils import to_utc, utc_now

logger = logging.getLogger(__name__)

ENGINE_NAME = "lifelong"

#: Enough evidence, over enough time, to call something long-running rather
#: than merely repeated. Both are required: eight occurrences inside one week
#: is a burst, and three across two years is thin but real.
HIGH_OCCURRENCES = 8
HIGH_SPAN_DAYS = 365
HIGH_ACTIVE_MONTHS = 6
MEDIUM_OCCURRENCES = 5


class LifelongEngine:
    """What recurred across the whole record, and when."""

    def __init__(self, user_id: int):
        self.user_id = user_id

    def analyze_all_themes(self) -> list[dict]:
        """Every theme with enough history to describe. Others are skipped.

        A theme is skipped rather than reported with a caveat: "three times in
        one week" is not a lifelong pattern, and dressing it as one with a low
        confidence label would still put it on the screen as history.
        """
        results = []
        for theme in themes.get_all_themes(self.user_id):
            try:
                found = self.analyze_theme(theme)
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(f"Lifelong analysis failed for theme {theme.get('id')}: {e}")
                continue
            if found:
                results.append(found)
        return results

    def analyze_theme(self, theme: dict) -> dict | None:
        occurrences = themes.get_occurrences(theme["id"])
        if len(occurrences) < LIFELONG_MIN_OCCURRENCES:
            return None

        moments = sorted(to_utc(o["occurred_at"]) for o in occurrences if o.get("occurred_at"))
        if len(moments) < LIFELONG_MIN_OCCURRENCES:
            return None

        first, last = moments[0], moments[-1]
        span_days = (last - first).days
        if span_days < LIFELONG_MIN_SPAN_DAYS:
            return None

        by_year = Counter(m.year for m in moments)
        densest_year, densest_count = by_year.most_common(1)[0]
        share = densest_count / len(moments)
        active_months = len({(m.year, m.month) for m in moments})
        days_since_last = (utc_now() - last).days

        return {
            "engine": ENGINE_NAME,
            "theme_id": theme["id"],
            # Both paths need these. The Insights service fills pattern_id with
            # a setdefault, but the chat pipeline does not, so an engine relying
            # on that patch-up works on one surface and raises on the other —
            # exactly the divergence ADR-0007 exists to prevent.
            "pattern_id": theme["id"],
            "pattern_type": "theme",
            "theme_summary": theme.get("summary") or "",
            "occurrence_count": len(moments),
            "lifelong_label": (
                "concentrated" if share >= LIFELONG_CONCENTRATION_SHARE else "spread"
            ),
            # The narrative formatter reads engine-specific label keys it knows
            # about and falls back to `label`. Emitting both keeps the engine to
            # the naming convention without the formatter needing a case for it.
            "label": (
                "concentrated" if share >= LIFELONG_CONCENTRATION_SHARE else "spread"
            ),
            "first_seen_at": first,
            "last_seen_at": last,
            "span_days": span_days,
            "active_months": active_months,
            "densest_year": densest_year,
            "densest_count": densest_count,
            "share_in_densest": round(share, 3),
            "days_since_last": days_since_last,
            "confidence_level": _confidence(len(moments), span_days, active_months),
            # The exemption this scale exists for. It describes a span, so a
            # quiet month does not make it untrue (agent/coverage.py).
            "claims_present": False,
        }


def _confidence(occurrences: int, span_days: int, active_months: int) -> str:
    """How much record stands behind the count.

    Occurrences alone are not enough: the same number spread over two years and
    crammed into one month say different things about how long-running a pattern
    is, so span and the number of distinct months both count.
    """
    if (occurrences >= HIGH_OCCURRENCES and span_days >= HIGH_SPAN_DAYS
            and active_months >= HIGH_ACTIVE_MONTHS):
        return "high"
    if occurrences >= MEDIUM_OCCURRENCES:
        return "medium"
    return "low"
