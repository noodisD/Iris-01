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

Occurrences in writing that carries no date are counted here and nowhere else.
This is the only reader that asks for them, because it is the only one that
measures without placing anything in a window. They are never added to the
number quoted beside a span — a count and the dates it supposedly falls inside
are two different measurements, and merging them would be the exact error
ADR-0009 names. A theme whose evidence is undated gets a count and no span at
all, which is less than a date would buy and more than silence.

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
        # The one reader in the system that wants undated occurrences. It counts
        # over the whole record without placing anything in a window, so an
        # occurrence with no date is still an occurrence here — while every
        # engine that measures per day keeps the dated-only default.
        occurrences = themes.get_occurrences(theme["id"], include_undated=True)
        if len(occurrences) < LIFELONG_MIN_OCCURRENCES:
            return None

        moments = sorted(to_utc(o["occurred_at"]) for o in occurrences if o.get("occurred_at"))
        undated = len(occurrences) - len(moments)

        if len(moments) < LIFELONG_MIN_OCCURRENCES:
            return self._count_only(theme, len(occurrences), undated)

        first, last = moments[0], moments[-1]
        span_days = (last - first).days
        if span_days < LIFELONG_MIN_SPAN_DAYS:
            return self._count_only(theme, len(occurrences), undated)

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
            # Counted, never folded into the headline. The span above covers
            # the dated occurrences only, so adding undated ones to the number
            # it is quoted beside would claim they fell inside it (ADR-0009).
            "undated_occurrences": undated,
            # Without this the sentence for a theme with twelve dated and twelve
            # undated occurrences read exactly as it did before the undated
            # ones existed, so what they added was computed and never shown.
            "template_variant": "with_undated" if undated else "default",
            "confidence_level": _confidence(len(moments), span_days, active_months),
            # The exemption this scale exists for. It describes a span, so a
            # quiet month does not make it untrue (agent/coverage.py).
            "claims_present": False,
        }

    def _count_only(self, theme: dict, total: int, undated: int) -> dict | None:
        """A count over writing that cannot be placed in time.

        Forty-three voice transcripts carry no date, and refusing to say
        anything about them would leave the largest single body of the owner's
        thinking unmeasured — which is the failure this scale was built to fix,
        arriving from the other direction.

        So it reports the count and stops. No span, no densest year, no "days
        since": those are not withheld out of caution, they do not exist. The
        finding carries no first_seen_at precisely so nothing downstream can
        fall back to describing it as recent, and its own template says plainly
        where the number came from.

        Requires that undated occurrences are actually the reason, so a theme
        with four dated occurrences inside one week is still skipped rather
        than re-reported here without its span.
        """
        if undated == 0 or total < LIFELONG_MIN_OCCURRENCES:
            return None
        return {
            "engine": ENGINE_NAME,
            "theme_id": theme["id"],
            "pattern_id": theme["id"],
            "pattern_type": "theme",
            "theme_summary": theme.get("summary") or "",
            "occurrence_count": total,
            "undated_occurrences": undated,
            "dated_occurrences": total - undated,
            "lifelong_label": "undated",
            "label": "undated",
            "span_is_undated": True,
            "template_variant": "undated",
            # Deliberately absent: first_seen_at, last_seen_at, span_days,
            # active_months, densest_year, days_since_last.
            "confidence_level": "low" if total < MEDIUM_OCCURRENCES else "medium",
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
