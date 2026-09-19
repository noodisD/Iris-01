"""Whether there is enough recent observation to say anything about *now*.

A claim about the present needs evidence from the present. The archive can be
large and the last entry months old: every theme then has an empty recent window
*and* an empty baseline, and the resolution engine reported all eighteen of the
owner's themes as "dissipated - 0 in 21d - 0 in the 90d before", eight of them at
medium confidence. That sentence is about a journal going quiet, not about a
person.

The rule: without COVERAGE_MIN_OBSERVED_DAYS days logged in the recent window,
nothing claims the present. One entry after months of silence is a sign of life,
not a basis for describing how things are. Both surfaces apply it (ADR-0007) - the chat context registers it as
a gate, the Insights screen calls it inside its admission policy - so chat cannot
say what the screen will not.

What is *withheld* is not what is *lost*: the themes, their occurrences and their
evidence stay exactly as they are, and return the moment there is recent writing
to compare them against.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from .constants import COVERAGE_MIN_OBSERVED_DAYS, RESOLUTION_RECENT_DAYS
from .database import db
from .timeutils import utc_now

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Coverage:
    """How much of the recent window the user was actually observed in."""

    window_days: int
    observed_days_in_window: int
    last_observed_day: date | None
    days_since_last: int | None
    #: False when the question could not be answered at all — a failed query is
    #: not an observation, and must not read as one.
    available: bool = True

    @property
    def supports_current_state(self) -> bool:
        return self.available and self.observed_days_in_window >= COVERAGE_MIN_OBSERVED_DAYS

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "windowDays": self.window_days,
            "observedDaysInWindow": self.observed_days_in_window,
            "observedDaysRequired": COVERAGE_MIN_OBSERVED_DAYS,
            "lastEntryOn": self.last_observed_day.isoformat() if self.last_observed_day else None,
            "daysSinceLastEntry": self.days_since_last,
            "supportsCurrentState": self.supports_current_state,
        }


def observation_coverage(user_id: int, window_days: int = RESOLUTION_RECENT_DAYS) -> Coverage:
    """What the recent window actually contains for this user.

    A failure to answer returns `available=False`, never a zero that reads like
    a measured absence — and never a silent pass.
    """
    now = utc_now()
    try:
        observed = db.count_observed_days(user_id, now - timedelta(days=window_days), now)
    except Exception as e:
        logger.error(f"Coverage unavailable for user {user_id}: {e}")
        return Coverage(window_days, 0, None, None, available=False)

    # The last day is display metadata. Losing it must not overturn a count we
    # already have.
    try:
        last = db.last_observed_day(user_id)
    except Exception as e:
        logger.warning(f"Last observed day unavailable for user {user_id}: {e}")
        last = None
    since = (now.date() - last).days if last else None
    return Coverage(window_days, observed, last, since)


def drop_unsupported(insights: list[dict]) -> list[dict]:
    """Remove findings the engines marked as not supported by their own evidence.

    A resolution over two empty windows is `unsupported`: it measured nothing, so
    it is a non-finding at every confidence preference, not a low-confidence one.
    Filtering it on the Insights screen alone left it reaching chat whenever the
    user's threshold was `low`.
    """
    return [
        i for i in insights
        if i.get("current_state_supported") is not False
        and i.get("resolution_label") != "unsupported"
        and i.get("label") != "unsupported"
    ]


def claims_present(insight: dict) -> bool:
    """Whether this finding says something about how things are *now*.

    Defaults to True, which is the safe reading: a finding that has not said
    otherwise is treated as a claim about the present and gated accordingly. A
    finding that forgets to declare itself is withheld, never admitted.
    """
    return insight.get("claims_present", True) is not False


def current_state_gate(insights: list[dict], context: dict) -> list[dict]:
    """Withhold present-tense findings while nothing recent has been logged.

    Shaped as a pipeline gate (insights, context) -> insights so the chat
    pipeline can register it beside enablement and confidence.

    Findings about a *span* are exempt, and that is the point of the exemption
    rather than a loophole in it. "Twelve times across two years, none since
    March" needs no recent writing to be true; withholding it because this month
    is quiet would suppress a fact precisely when it is most worth knowing. What
    stays gated is the present tense: anything claiming how things *are*.
    """
    user_id = context.get("user_id")
    if user_id is None or not insights:
        return insights

    try:
        insights = drop_unsupported(insights)
        coverage = observation_coverage(user_id)
    except Exception as e:
        # Fail closed. The pipeline catches a gate's exception and keeps the
        # candidates, so raising here would admit exactly what this gate exists
        # to withhold.
        logger.error(f"Coverage gate failed for user {user_id}, withholding: {e}")
        return []

    if coverage.supports_current_state:
        return insights

    historical = [i for i in insights if not claims_present(i)]
    logger.info(
        f"Coverage gate: {len(insights) - len(historical)} present-tense finding(s) withheld, "
        f"{len(historical)} about a span kept - "
        f"{coverage.observed_days_in_window} of {COVERAGE_MIN_OBSERVED_DAYS} days logged in the last "
        f"{coverage.window_days} (last entry {coverage.last_observed_day}, available={coverage.available})"
    )
    return historical
