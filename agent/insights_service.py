"""
Insights Service — translation layer from the analytical engines to the
frontend's InsightSummary / InsightDetail contract.

The engines emit metric dicts (recent/past counts, labels, confidence levels)
per pattern; this service normalizes them into the wire shape the frontend
expects. Snooze/resolve/seen state is overlaid from the insight_status table.

Insight IDs are stable across recomputes (`{engine}:{pattern_key}`) so persisted
status survives the on-the-fly recomputation.
"""

import logging
from datetime import UTC, datetime

from .coverage import observation_coverage
from .narrative_policy import FORBIDDEN_REGEX
from .constants import (
    DECISION_IMPACT_BASELINE_DAYS,
    DECISION_IMPACT_WINDOW_DAYS,
    LEVERAGE_TIME_LAG_DAYS,
    LEVERAGE_WINDOW_DAYS,
    RESOLUTION_BASELINE_DAYS,
    RESOLUTION_RECENT_DAYS,
    TENSION_BASELINE_DAYS,
    TENSION_RECENT_DAYS,
    TRAJECTORY_BASELINE_DAYS,
    TRAJECTORY_RECENT_DAYS,
)
from .database import db
from .pipeline_orchestrator import admit_findings, collect_findings

logger = logging.getLogger(__name__)

# No engine performs causal identification. Leverage measures whether one theme
# tends to *precede* another within a lag window, and decision impact compares
# rates before and after an anchor: both are temporal association, and labelling
# them "causal" on screen asserted something the mathematics never established.
# The kicker says which measurement a card is, in words, the way Settings names
# the engines. Five of them used to share "temporal", which told the owner
# nothing about the difference between a two-year count and a fortnight's slope.
KIND_MAP = {
    "lifelong": "across the record",
    "trajectory": "direction",
    "resolution": "still here or gone quiet",
    # It counts days two themes share — a co-occurrence, not anything about
    # words, which is what the old kicker claimed on every tension card.
    "tension": "co-occurrence",
    "leverage": "which comes first",
    "decision_impact": "before and after",
}

# An ordinal encoding of the confidence *label*, not a calibrated probability —
# the contract field is typed as a number. The label itself is carried in `tags`
# and in the detail callout so the screen shows the real thing.
CONFIDENCE_MAP = {"low": 0.4, "medium": 0.65, "high": 0.9}
ACCENTS = ["sage", "rose", "indigo", "amber"]


def _measure(label: str, value, sub: str | None = None) -> dict:
    """One reported number, with the interval or denominator it came from.

    Every engine used to be flattened into "recent vs earlier" counts. Only two
    of them measure that, so the other three had a real number moved into the
    "recent" slot and a zero invented for "earlier" — the screen then read
    "12 recent · 0 earlier" for a tension whose actual split was 4 and 8.
    A measure names what it counted and over what window instead.
    """
    return {"label": label, "value": value, "sub": sub}


def _describes_span(raw: dict) -> bool:
    """A finding about a stretch of the past rather than about now.

    The engine's own `claims_present: False` — the same flag that earns it the
    coverage gate's exemption — decides the tense it is described in.
    """
    return raw.get("claims_present") is False


def _lifelong_card(r: dict) -> tuple[list, str]:
    """The measures and headline for one lifelong finding.

    Two shapes, because the engine reports two kinds of finding. A dated one
    has a span, a densest year and a last occurrence. A count-only one has
    none of those — not withheld, absent — because its evidence cannot be
    placed in time. This read all of them with hard subscripts, so the first
    count-only finding raised KeyError and stopped the loop: the Insights page
    silently lost exactly the findings that exist only because of undated
    writing, and, since findings arrive sorted by dated count, would have lost
    every card after them too had one sorted earlier.

    Undated occurrences get their own labelled row in both shapes. They are
    never added into a number quoted beside a span (ADR-0009).
    """
    undated = r.get("undated_occurrences", 0)
    undated_row = _measure("Without a date", undated, "no span, so not in the months above")

    if r.get("lifelong_label") == "undated":
        measures = [_measure("Occurrences", r["occurrence_count"], "in all writing")]
        dated = r.get("dated_occurrences", 0)
        if dated:
            measures.append(_measure("With a date", dated, "too few for a span"))
        measures.append(_measure("Without a date", undated, None))
        return measures, f"{r['occurrence_count']} times · {undated} without a date"

    months = max(1, r["span_days"] // 30)
    measures = [
        _measure("Occurrences", r["occurrence_count"], f"over {months} months"),
        _measure(f"In {r['densest_year']}", r["densest_count"],
                 f"{r['share_in_densest']:.0%} of them"),
        _measure("Months with entries", r["active_months"], None),
    ]
    headline = (f"{r['occurrence_count']} times across {months} months · "
                f"last {r['days_since_last']}d ago")
    if undated:
        measures.append(undated_row)
        headline += f" · {undated} more undated"
    return measures, headline


def _relative_change(delta) -> str:
    """Render a decision-impact delta as the relative change it is."""
    if delta is None:
        return "change following the anchor"
    return f"{float(delta):+.0%} relative change in rate"


def _iso(ts) -> str:
    if ts is None:
        return datetime.now(UTC).isoformat()
    if isinstance(ts, datetime):
        return ts.isoformat()
    return str(ts)


# --- cards: one finding, as the screen shows it ------------------------------
#
# Each takes a finding exactly as the engines produced it and the shared
# admission passed it (agent/pipeline_orchestrator.py). Moved verbatim from the
# per-engine loops that used to call the engines themselves: the screen now
# renders what was admitted instead of collecting its own.

def _lifelong_to_card(r: dict) -> dict | None:
    measures, headline = _lifelong_card(r)
    return {
        "engine": "lifelong",
        "pattern_key": r.get("pattern_key") or str(r["theme_id"]),
        "theme_id": r["theme_id"],
        "summary": r.get("theme_summary") or "",
        "label": r.get("lifelong_label") or "observed",
        "measures_label": "Across the whole record",
        "measures": measures,
        "headline_metric": headline,
        "confidence_level": r.get("confidence_level", "low"),
        # Describes a span, so a quiet recent window does not make it
        # untrue — the coverage gate lets it through (ADR-0007).
        "claims_present": False,
    }


def _trajectory_to_card(r: dict) -> dict | None:
    return {
        "engine": "trajectory",
        "pattern_key": r.get("pattern_key") or str(r["theme_id"]),
        "theme_id": r["theme_id"],
        "summary": r.get("theme_summary") or "",
        "label": r.get("trajectory_label") or "observed",
        "measures_label": "Occurrences by window",
        "measures": [
            _measure("Recent", r.get("recent_count", 0),
                     f"last {TRAJECTORY_RECENT_DAYS} days"),
            _measure("Earlier", r.get("past_count", 0),
                     f"prior {TRAJECTORY_BASELINE_DAYS} days"),
        ],
        "headline_metric": (
            f"{r.get('recent_count', 0)} in {TRAJECTORY_RECENT_DAYS}d · "
            f"{r.get('past_count', 0)} in the {TRAJECTORY_BASELINE_DAYS}d before"
        ),
        "confidence_level": r.get("confidence_level", "low"),
    }


def _resolution_to_card(r: dict) -> dict | None:
    if r.get("resolution_label") == "unsupported":
        return None  # both windows empty: nothing was compared
    return {
        "engine": "resolution",
        "pattern_key": r.get("pattern_key") or str(r["theme_id"]),
        "theme_id": r["theme_id"],
        "summary": r.get("summary") or "",
        "label": r.get("resolution_label") or "observed",
        "measures_label": "Occurrences by window",
        "measures": [
            _measure("Recent", r.get("recent_count", 0),
                     f"last {RESOLUTION_RECENT_DAYS} days"),
            _measure("Earlier", r.get("past_count", 0),
                     f"prior {RESOLUTION_BASELINE_DAYS} days"),
        ],
        "headline_metric": (
            f"{r.get('recent_count', 0)} in {RESOLUTION_RECENT_DAYS}d · "
            f"{r.get('past_count', 0)} in the {RESOLUTION_BASELINE_DAYS}d before"
        ),
        "confidence_level": r.get("confidence_level", "low"),
    }


def _tension_to_card(r: dict) -> dict | None:
    a, b = r.get("theme_a_id"), r.get("theme_b_id")
    return {
        "engine": "tension",
        "pattern_key": r.get("pattern_key") or f"{a}-{b}",
        "theme_id": a,
        "pair_of": (a, b),
        "summary": f"{r.get('theme_a_summary','')} vs {r.get('theme_b_summary','')}".strip(),
        "label": r.get("tension_label") or "tension",
        # The engine already returns the recent/earlier split; this
        # adapter was passing the all-time total as "recent" and
        # hardcoding zero for "earlier".
        "measures_label": "Days both themes appeared",
        "measures": [
            _measure("Recent", r.get("recent_cooccurrence_count", 0),
                     f"last {TENSION_RECENT_DAYS} days"),
            _measure("Earlier", r.get("past_cooccurrence_count", 0),
                     f"prior {TENSION_BASELINE_DAYS} days"),
            _measure("All time", r.get("cooccurrence_count", 0), None),
        ],
        "headline_metric": (
            f"{r.get('recent_cooccurrence_count', 0)} shared days in "
            f"{TENSION_RECENT_DAYS}d · "
            f"{r.get('past_cooccurrence_count', 0)} before"
        ),
        "confidence_level": r.get("confidence_level", "low"),
    }


def _leverage_to_card(r: dict) -> dict | None:
    s, t = r.get("source_id"), r.get("target_id")
    return {
        "engine": "leverage",
        "pattern_key": r.get("pattern_key") or f"{s}-{t}",
        "theme_id": s,
        "pair_of": (s, t),
        "summary": f"{r.get('source_summary','')} → {r.get('target_summary','')}".strip(),
        # "influence" overstated it: this is a forward/reverse
        # co-occurrence proportion within a lag window.
        "label": "associated",
        "measures_label": "Temporal association",
        "measures": [
            _measure("Directional lift",
                     round(float(r.get("directional_lift") or 0.0), 2),
                     f"forward vs reverse within {LEVERAGE_TIME_LAG_DAYS} days"),
            _measure("Association score",
                     round(float(r.get("influence_score") or 0.0), 2), None),
            _measure("Co-occurrences", r.get("cooccurrence_count", 0),
                     f"last {LEVERAGE_WINDOW_DAYS} days"),
        ],
        "headline_metric": (
            f"{r.get('cooccurrence_count', 0)} co-occurrences within "
            f"{LEVERAGE_TIME_LAG_DAYS}d"
        ),
        "confidence_level": r.get("confidence_level", "low"),
    }


def _decision_impact_to_card(r: dict) -> dict | None:
    a, t = r.get("anchor_id"), r.get("target_id")
    return {
        "engine": "decision_impact",
        "pattern_key": r.get("pattern_key") or f"{a}-{t}",
        "theme_id": a,
        "pair_of": (a, t),
        "summary": f"{r.get('anchor_summary','')} → {r.get('target_summary','')}".strip(),
        "label": r.get("effect_direction") or "shift",
        # target_total_count is every occurrence the target has ever
        # had, not post-anchor support, so it was not a "recent"
        # count and there was never an "earlier" one to compare it to.
        "measures_label": "Change following the anchor",
        "measures": [
            _measure("Relative change in rate",
                     round(float(r.get("delta_score") or 0.0), 2),
                     f"{DECISION_IMPACT_WINDOW_DAYS}d after vs "
                     f"{DECISION_IMPACT_BASELINE_DAYS}d before each anchor"),
            _measure("Direction agreement",
                     round(float(r.get("consistency_ratio") or 0.0), 2),
                     "across anchor events"),
            _measure("Target occurrences", r.get("target_total_count", 0),
                     "all time"),
        ],
        "headline_metric": _relative_change(r.get("delta_score")),
        "confidence_level": r.get("confidence_level", "low"),
    }


_CARD_BUILDERS = {
    "lifelong": _lifelong_to_card,
    "trajectory": _trajectory_to_card,
    "resolution": _resolution_to_card,
    "tension": _tension_to_card,
    "leverage": _leverage_to_card,
    "decision_impact": _decision_impact_to_card,
}

class InsightsService:
    """Fans out across the engines and normalizes results to the contract."""

    def __init__(self, user_id: int):
        self.user_id = user_id

    # --- raw normalization -------------------------------------------------

    # --- findings -------------------------------------------------------------

    def _findings(self) -> list[dict]:
        """What the engines found: the same collection chat admits from."""
        return collect_findings(self.user_id)

    @staticmethod
    def _to_card(finding: dict) -> dict | None:
        builder = _CARD_BUILDERS.get(finding.get("engine_name"))
        return builder(finding) if builder else None

    def _normalize(self) -> list:
        """Every finding as a card, admitted or not.

        Policy governs what is surfaced, not what is addressable (ADR-0007):
        following a link to one insight should still open it.
        """
        return [c for c in (self._to_card(f) for f in self._findings()) if c]

    def _admitted(self) -> list[dict]:
        """The cards the list shows: chat's admission, without chat's budget.

        This used to be a second copy of the policy — enablement, confidence and
        conflict re-implemented here in a different order, over findings this
        screen collected for itself at a different grain, sorted by confidence
        label and never ranked. Now it is the same function chat calls. The
        budget is the one step left out: that is a limit on how much fits in a
        prompt, and this is a list the owner scrolls.
        """
        admission = admit_findings(self._findings(), self.user_id)
        # Recorded so an empty screen can name its reason. "Nothing to show"
        # because the owner's filter hid it is a different sentence from
        # "nothing was found", and the screen must not merge the two.
        self.policy_counts = {
            "suppressed_by_filter": admission.held_back_by_owner,
            "conflict_suppressed": len(admission.conflicts),
            "admitted": len(admission.findings),
        }
        return [c for c in (self._to_card(f) for f in admission.findings) if c]

    # --- contract building -------------------------------------------------

    def _summary(self, raw: dict, idx: int, status_row: dict | None, detected_at: str) -> dict:
        seen = bool(status_row and status_row.get("seen"))
        return {
            "id": f"{raw['engine']}:{raw['pattern_key']}",
            "kind": KIND_MAP[raw["engine"]],
            "status": "active" if seen else "new",
            "headline": {
                "line1": (raw["summary"] or "A pattern")[:48],
                # A span is described in the past tense. "Is spread" read a
                # two-year count as though it were how things are this morning,
                # for the one engine whose point is that it claims nothing
                # about now (it passes the coverage gate on that promise).
                "line2": (f"recurred · {raw['label']}" if _describes_span(raw)
                          else f"is {raw['label']}"),
                "line3": self._headline_metric(raw),
            },
            "summary": f'"{raw["summary"]}" — {raw["label"]}. '
                       f'{self._headline_metric(raw)}.',
            "accentColor": ACCENTS[idx % len(ACCENTS)],
            "featured": idx == 0,
            "tags": [raw["label"], f"{raw['confidence_level']} confidence"],
            "confidence": CONFIDENCE_MAP.get(raw["confidence_level"], 0.4),
            "detectedAt": detected_at,
            "seen": seen,
            # Where this came from, and what its count means. A construct the
            # owner read and vouched for was indistinguishable on screen from a
            # cluster a machine named after the fact, which defeats the point of
            # asking them. And a 'mention' count says the subject appears in the
            # writing — never how often they did the thing.
            # A finding about two themes has no single origin, so it shows
            # none. `theme_id` carries the first of the pair for evidence
            # lookups, and reading provenance from it put one theme's origin
            # and claim kind on a card about both — a clustered/confirmed pair
            # read as though the owner had vouched for the whole thing.
            **({} if raw.get("pair_of") else self._provenance(raw.get("theme_id"))),
        }

    def _provenance(self, theme_id) -> dict:
        """How a finding was arrived at, carried through to the screen.

        Absent rather than guessed when the finding is not theme-shaped: tension,
        leverage and decision impact span two patterns, so a single origin would
        be a fiction. The caller decides by `pair_of`; this used to be reached
        with the pair's first theme, which is exactly the fiction it describes.
        """
        if not isinstance(theme_id, int):
            return {}
        try:
            theme = db.get_theme_by_id(theme_id)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Provenance unavailable for theme {theme_id}: {e}")
            return {}
        if not theme:
            return {}
        return {
            "origin": theme.get("origin"),
            "claimKind": theme.get("claim_kind"),
            "confirmedAt": _iso(theme["confirmed_at"]) if theme.get("confirmed_at") else None,
        }

    def coverage(self) -> dict:
        """Why the list may be empty: how much recent evidence there is.

        An empty Insights screen has two very different meanings - nothing has
        been noticed, or nothing recent has been written - and the screen said
        the first while the second was true.
        """
        out = observation_coverage(self.user_id).as_dict()
        with db.connection() as conn, conn.cursor() as cur:
            # Everything the owner wrote. A journal entry is a reflection
            # (ADR-0010); the separate legacy table is gone (migration 0015).
            cur.execute(
                "SELECT count(*) FROM reflections WHERE user_id = %s;",
                (self.user_id,),
            )
            out["entries"] = cur.fetchone()[0]
            # Keyed on (source_type, source_id): the same number identifies a
            # different row in each source table, so counting ids alone merges a
            # reflection with a habit completion that happens to share one.
            # Only what is actually measured. Candidate constructs exist as theme
            # rows so they can be reviewed, and counting them told the owner they
            # had 28 themes when 18 were being measured — inflating the account's
            # totals with proposals nobody had agreed to yet.
            cur.execute(
                """SELECT count(DISTINCT t.id),
                          count(DISTINCT (o.source_type, o.source_id))
                     FROM themes t LEFT JOIN theme_occurrences o ON o.theme_id = t.id
                    WHERE t.user_id = %s AND t.status = 'active';""",
                (self.user_id,),
            )
            out["themes"], out["entriesInThemes"] = cur.fetchone()
            # Reported separately, never added in: a proposal is not a finding.
            cur.execute(
                "SELECT count(*) FROM themes WHERE user_id = %s AND status = 'candidate';",
                (self.user_id,),
            )
            out["candidateConstructs"] = cur.fetchone()[0]

        # Which of the remaining reasons applies: a filter the owner set, or
        # findings they have already dealt with.
        try:
            admitted = self._admitted()
            statuses = db.get_insight_statuses(self.user_id)
            now = datetime.now(UTC)
            hidden = 0
            for item in admitted:
                st = statuses.get(f"{item['engine']}:{item['pattern_key']}")
                if not st:
                    continue
                snoozed_until = st.get("snoozed_until")
                if st.get("status") == "resolved" or (
                        st.get("status") == "snoozed" and snoozed_until and snoozed_until > now):
                    hidden += 1
            out["admitted"] = len(admitted)
            out["hiddenByStatus"] = hidden
            out["suppressedByFilter"] = getattr(self, "policy_counts", {}).get("suppressed_by_filter", 0)
        except Exception as e:
            # Unknown, which is not the same as none. Nulls keep the screen from
            # announcing a reason it did not establish.
            logger.warning(f"Policy breakdown unavailable for user {self.user_id}: {e}")
            out["admitted"] = out["hiddenByStatus"] = out["suppressedByFilter"] = None
        return out

    def list_summaries(self) -> list:
        """Return InsightSummary[], hiding resolved and still-snoozed insights."""
        statuses = db.get_insight_statuses(self.user_id)
        now = datetime.now(UTC)
        detected = now.isoformat()
        summaries = []
        idx = 0
        # get_summary/get_detail deliberately do not filter: policy governs what
        # is *surfaced*, not what is *addressable* — following a link to one
        # specific insight should still show it.
        for raw in self._admitted():
            iid = f"{raw['engine']}:{raw['pattern_key']}"
            s = statuses.get(iid)
            if s:
                if s.get("status") == "resolved":
                    continue
                snz = s.get("snoozed_until")
                if s.get("status") == "snoozed" and snz and snz > now:
                    continue
            summaries.append(self._summary(raw, idx, s, detected))
            idx += 1
        return summaries

    def get_summary(self, insight_id: str, force_status: str | None = None) -> dict | None:
        """Return one InsightSummary regardless of snooze/resolve filtering.

        Used by snooze/resolve responses, where `force_status` overrides the
        displayed status to reflect the action just taken."""
        statuses = db.get_insight_statuses(self.user_id)
        detected = datetime.now(UTC).isoformat()
        for idx, raw in enumerate(self._normalize()):
            iid = f"{raw['engine']}:{raw['pattern_key']}"
            if iid != insight_id:
                continue
            summary = self._summary(raw, idx, statuses.get(iid), detected)
            if force_status:
                summary["status"] = force_status
            return summary
        return None

    def get_detail(self, insight_id: str) -> dict | None:
        """Return InsightDetail for one insight, or None if not found."""
        statuses = db.get_insight_statuses(self.user_id)
        detected = datetime.now(UTC).isoformat()
        for idx, raw in enumerate(self._normalize()):
            iid = f"{raw['engine']}:{raw['pattern_key']}"
            if iid != insight_id:
                continue
            base = self._summary(raw, idx, statuses.get(iid), detected)
            # A link kept working is not a licence to read as current: policy
            # governs what is surfaced, not what is addressable (ADR-0007), so
            # the qualification travels with the insight.
            coverage = observation_coverage(self.user_id)
            if not coverage.supports_current_state:
                base["historical"] = True
                base["coverageNote"] = (
                    f"Historical. Only {coverage.observed_days_in_window} of the "
                    f"{coverage.window_days} most recent days were written in, so this "
                    "describes what was recorded then, not how things are now."
                )
            base.update({
                "irisRead": self._iris_read(raw),
                "evidence": self._evidence(raw),
                "pullQuotes": self._pull_quotes(raw),
                "related": [],
                "suggestions": [],
                "methodology": self._methodology(raw["engine"]),
            })
            return base
        return None

    # --- detail helpers ----------------------------------------------------

    @staticmethod
    def _headline_metric(raw: dict) -> str:
        """The one number that belongs in the headline, or nothing.

        Falls back to the label when an engine reports no headline measure,
        rather than manufacturing a comparison to fill the slot.
        """
        return raw.get("headline_metric") or str(raw.get("label") or "observed")

    def _iris_read(self, raw: dict) -> str:
        """What IRIS observed, in the engine's own terms.

        This used to assert "that shift is what caught my attention" for every
        engine, including the three that never measured a shift.
        """
        if _describes_span(raw) and raw["label"] == "undated":
            opening = (f'"{raw["summary"]}" recurred in writing that carries no date, '
                       f'so no span can be given.')
        elif _describes_span(raw):
            opening = (f'Across the whole record, "{raw["summary"]}" recurred, and its '
                       f'occurrences were {raw["label"]}.')
        else:
            opening = f'I keep noticing "{raw["summary"]}". It reads as {raw["label"]}.'
        parts = [opening]
        for m in raw.get("measures", []):
            window = f" ({m['sub']})" if m.get("sub") else ""
            parts.append(f"{m['label']}: {m['value']}{window}.")
        parts.append(
            f"That is {raw['confidence_level']} confidence on the evidence logged so far."
        )
        # The firewall ran on chat's templates and nowhere else, and this text
        # carries a theme's summary — written by a model after the fact. A
        # sentence that says what caused what, or what to do, is dropped here
        # as it would be there.
        return " ".join(p for p in parts if not FORBIDDEN_REGEX.search(p))

    def _evidence(self, raw: dict) -> list:
        """Only what the engine measured, each value labelled with its window."""
        evidence: list = []
        measures = raw.get("measures", [])
        if measures:
            evidence.append({
                "kind": "comparison",
                "label": raw.get("measures_label") or "Measured",
                "items": [
                    {"label": m["label"], "value": m["value"],
                     **({"sub": m["sub"]} if m.get("sub") else {})}
                    for m in measures
                ],
            })
        evidence.append({
            "kind": "callout",
            "label": "Read",
            "value": str(raw["label"]),
            "sub": f"{raw['confidence_level']} confidence",
        })
        return evidence

    def _pull_quotes(self, raw: dict) -> list:
        theme_id = raw.get("theme_id")
        if not isinstance(theme_id, int):
            return []
        quotes = []
        try:
            for occ in db.get_theme_occurrences(theme_id)[:3]:
                snippet = occ.get("snippet")
                if not snippet:
                    continue
                src = (occ.get("source_type") or "").lower()
                kind = "journal" if ("journal" in src or "reflection" in src) else "chat"
                occurred = occ.get("occurred_at")
                # The id the journal can open. A quote the owner cannot go and
                # check is an assertion about their writing, not a citation.
                # Only reflections are addressable there, so nothing else
                # pretends to be a link.
                source_id = occ.get("source_id")
                quotes.append({
                    "sourceDate": _iso(occurred)[:10],
                    "text": snippet,
                    "sourceKind": kind,
                    "sourceId": (str(source_id) if "reflection" in src
                                 and source_id is not None else None),
                })
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Pull quotes unavailable for theme {theme_id}: {e}")
        return quotes

    def _methodology(self, engine: str) -> str:
        return {
            "trajectory": "Compares how often a theme appears in a recent window "
                          "against an earlier baseline window to detect rising or fading trends.",
            "resolution": "Measures whether a theme that was once frequent has "
                          "dissipated, stabilized, or reappeared.",
            "tension": "Looks at how two themes co-occur and diverge over time to "
                       "surface patterns that sit uneasily together.",
            "leverage": "Counts how often one theme is followed by another within a "
                        "short lag, in each direction. This is temporal association, "
                        "not a measure of one theme causing the other.",
            "decision_impact": "Compares how often a theme occurs in the period "
                               "following an anchor pattern against the period "
                               "before it. The direction is the *average* of "
                               "those rates across every anchor whose follow-up "
                               "window has fully elapsed, so one unusual episode "
                               "can carry it; the confidence beside it says how "
                               "many of the episodes agree with that direction, "
                               "and counts the writing they actually saw rather "
                               "than the windows that saw it. Association over "
                               "time, not cause.",
            "lifelong": "Counts every occurrence of the theme across the whole "
                        "record: when it first and last appeared, the year that "
                        "holds most of them, and how long since the last. "
                        "Occurrences in writing with no date are counted "
                        "separately and never placed in the span. It describes "
                        "the past and makes no claim about how things are now.",
        }.get(engine, "Derived from longitudinal pattern analysis over your entries.")
