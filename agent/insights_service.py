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

from .conflict import ConflictSuppressionEngine
from .coverage import current_state_gate, drop_unsupported, observation_coverage
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
from .decision_impact import DecisionImpactEngine
from .leverage import LeverageEngine
from .lifelong import LifelongEngine
from .preferences import UserPreferencesService
from .resolution import ResolutionEngine
from .tension import TensionEngine
from .trajectory import TrajectoryEngine

logger = logging.getLogger(__name__)

# No engine performs causal identification. Leverage measures whether one theme
# tends to *precede* another within a lag window, and decision impact compares
# rates before and after an anchor: both are temporal association, and labelling
# them "causal" on screen asserted something the mathematics never established.
KIND_MAP = {
    "lifelong": "temporal",
    "trajectory": "temporal",
    "resolution": "temporal",
    "tension": "linguistic",
    "leverage": "temporal",
    "decision_impact": "temporal",
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


class InsightsService:
    """Fans out across the engines and normalizes results to the contract."""

    def __init__(self, user_id: int):
        self.user_id = user_id

    # --- raw normalization -------------------------------------------------

    def _normalize(self) -> list:
        """Collect normalized {engine, pattern_key, summary, label, measures,
        confidence_level, theme_id} dicts across the engines. Engines that fail
        or have no data are skipped so a partial backend still yields insights.

        `measures` is engine-specific: what that engine actually computed, each
        value carrying the window it was measured over. Engines that do not
        compare a recent window against an earlier one do not report one."""
        out = []

        try:
            for r in LifelongEngine(self.user_id).analyze_all_themes():
                months = max(1, r["span_days"] // 30)
                out.append({
                    "engine": "lifelong",
                    "pattern_key": str(r["theme_id"]),
                    "theme_id": r["theme_id"],
                    "summary": r.get("theme_summary") or "",
                    "label": r.get("lifelong_label") or "observed",
                    "measures_label": "Across the whole record",
                    "measures": [
                        _measure("Occurrences", r["occurrence_count"],
                                 f"over {months} months"),
                        _measure(f"In {r['densest_year']}", r["densest_count"],
                                 f"{r['share_in_densest']:.0%} of them"),
                        _measure("Months with entries", r["active_months"], None),
                    ],
                    "headline_metric": (
                        f"{r['occurrence_count']} times across {months} months · "
                        f"last {r['days_since_last']}d ago"
                    ),
                    "confidence_level": r.get("confidence_level", "low"),
                    # Describes a span, so a quiet recent window does not make it
                    # untrue — the coverage gate lets it through (ADR-0007).
                    "claims_present": False,
                })
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Lifelong insights unavailable: {e}")

        try:
            for r in TrajectoryEngine(self.user_id).analyze_all_themes():
                out.append({
                    "engine": "trajectory",
                    "pattern_key": str(r["theme_id"]),
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
                })
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Trajectory insights unavailable: {e}")

        try:
            for r in ResolutionEngine(self.user_id).analyze_all_themes():
                if r.get("resolution_label") == "unsupported":
                    continue  # both windows empty: nothing was compared
                out.append({
                    "engine": "resolution",
                    "pattern_key": str(r["theme_id"]),
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
                })
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Resolution insights unavailable: {e}")

        try:
            for r in TensionEngine(self.user_id).analyze_all_tensions():
                a, b = r.get("theme_a_id"), r.get("theme_b_id")
                out.append({
                    "engine": "tension",
                    "pattern_key": f"{a}-{b}",
                    "theme_id": a,
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
                })
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Tension insights unavailable: {e}")

        try:
            for r in LeverageEngine(self.user_id).analyze_all_leverage():
                s, t = r.get("source_id"), r.get("target_id")
                out.append({
                    "engine": "leverage",
                    "pattern_key": f"{s}-{t}",
                    "theme_id": s,
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
                })
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Leverage insights unavailable: {e}")

        try:
            for r in DecisionImpactEngine(self.user_id).analyze_all_anchors():
                a, t = r.get("anchor_id"), r.get("target_id")
                out.append({
                    "engine": "decision_impact",
                    "pattern_key": f"{a}-{t}",
                    "theme_id": a,
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
                })
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Decision-impact insights unavailable: {e}")

        return out

    # --- admission policy --------------------------------------------------

    def _apply_policy(self, raw: list[dict]) -> list[dict]:
        """Apply the admission policy the chat context uses.

        The Insights screen and the chat context are two answers to the same
        question — what has IRIS noticed — and they must not disagree. This
        service called the engines directly with no gating at all, so a finding
        suppressed in chat as low-confidence or self-contradictory was still
        presented on screen as something IRIS believed.

        The user's own preferences apply: disabled engines and anything below
        their confidence threshold are dropped, then conflict suppression
        removes contradictions. The budget is deliberately *not* applied — that
        is a limit on how much fits in an LLM prompt, not a statement about what
        is true, and this screen is a list the user scrolls. Ordering by
        strength replaces truncation.
        """
        # A finding about now needs something logged now, and a finding its own
        # engine calls unsupported is a non-finding at any threshold (ADR-0007:
        # the same rule the chat pipeline applies as a gate).
        raw = current_state_gate(drop_unsupported(raw), {"user_id": self.user_id})

        prefs = UserPreferencesService(self.user_id).get_prefs()
        levels = {"low": 0, "medium": 1, "high": 2}
        minimum = levels.get(prefs.get("min_confidence", "medium"), 1)
        enabled = prefs.get("enabled_engines")

        admitted = []
        filtered_out = 0
        for item in raw:
            if enabled is not None and item["engine"] not in enabled:
                filtered_out += 1
                continue
            if levels.get(item.get("confidence_level", "low"), 0) < minimum:
                filtered_out += 1
                continue
            admitted.append(item)

        # Conflict suppression reads the pipeline's field names.
        for item in admitted:
            item.setdefault("pattern_type", "theme")
            item.setdefault("pattern_id", item.get("theme_id"))
            item.setdefault("engine_name", item["engine"])
            item.setdefault(f"{item['engine']}_label", item.get("label"))

        visible = ConflictSuppressionEngine().suppress(admitted)["visible"]
        visible.sort(key=lambda i: levels.get(i.get("confidence_level", "low"), 0), reverse=True)
        # Recorded so an empty screen can name its reason. "Nothing to show"
        # because the owner's filter hid it is a different sentence from
        # "nothing was found", and the screen must not merge the two.
        self.policy_counts = {
            "suppressed_by_filter": filtered_out,
            "conflict_suppressed": len(admitted) - len(visible),
            "admitted": len(visible),
        }
        return visible

    # --- contract building -------------------------------------------------

    def _summary(self, raw: dict, idx: int, status_row: dict | None, detected_at: str) -> dict:
        seen = bool(status_row and status_row.get("seen"))
        return {
            "id": f"{raw['engine']}:{raw['pattern_key']}",
            "kind": KIND_MAP.get(raw["engine"], "temporal"),
            "status": "active" if seen else "new",
            "headline": {
                "line1": (raw["summary"] or "A pattern")[:48],
                "line2": f"is {raw['label']}",
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
            **self._provenance(raw.get("theme_id")),
        }

    def _provenance(self, theme_id) -> dict:
        """How a finding was arrived at, carried through to the screen.

        Absent rather than guessed when the finding is not theme-shaped: tension
        and leverage span two patterns, so a single origin would be a fiction.
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
            # Everything the owner deliberately logged, by ADR-0003's definition
            # of evidence — not reflections alone.
            cur.execute(
                """SELECT (SELECT count(*) FROM reflections WHERE user_id = %s)
                        + (SELECT count(*) FROM journal_entries WHERE user_id = %s);""",
                (self.user_id, self.user_id),
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
            admitted = self._apply_policy(self._normalize())
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
        for raw in self._apply_policy(self._normalize()):
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
        parts = [f'I keep noticing "{raw["summary"]}". It reads as {raw["label"]}.']
        for m in raw.get("measures", []):
            window = f" ({m['sub']})" if m.get("sub") else ""
            parts.append(f"{m['label']}: {m['value']}{window}.")
        parts.append(
            f"That is {raw['confidence_level']} confidence on the evidence logged so far."
        )
        return " ".join(parts)

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
                               "before it. Association over time, not cause.",
        }.get(engine, "Derived from longitudinal pattern analysis over your entries.")
