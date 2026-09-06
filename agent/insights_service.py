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

from .database import db
from .decision_impact import DecisionImpactEngine
from .leverage import LeverageEngine
from .resolution import ResolutionEngine
from .tension import TensionEngine
from .trajectory import TrajectoryEngine

logger = logging.getLogger(__name__)

KIND_MAP = {
    "trajectory": "temporal",
    "resolution": "temporal",
    "tension": "linguistic",
    "leverage": "causal",
    "decision_impact": "causal",
}
CONFIDENCE_MAP = {"low": 0.4, "medium": 0.65, "high": 0.9}
ACCENTS = ["sage", "rose", "indigo", "amber"]


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
        """Collect normalized {engine, pattern_key, summary, label, recent, past,
        confidence_level, theme_id} dicts across the engines. Engines that fail
        or have no data are skipped so a partial backend still yields insights."""
        out = []

        try:
            for r in TrajectoryEngine(self.user_id).analyze_all_themes():
                out.append({
                    "engine": "trajectory",
                    "pattern_key": str(r["theme_id"]),
                    "theme_id": r["theme_id"],
                    "summary": r.get("theme_summary") or "",
                    "label": r.get("trajectory_label") or "observed",
                    "recent": r.get("recent_count", 0),
                    "past": r.get("past_count", 0),
                    "confidence_level": r.get("confidence_level", "low"),
                })
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Trajectory insights unavailable: {e}")

        try:
            for r in ResolutionEngine(self.user_id).analyze_all_themes():
                out.append({
                    "engine": "resolution",
                    "pattern_key": str(r["theme_id"]),
                    "theme_id": r["theme_id"],
                    "summary": r.get("summary") or "",
                    "label": r.get("resolution_label") or "observed",
                    "recent": r.get("recent_count", 0),
                    "past": r.get("past_count", 0),
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
                    "recent": r.get("cooccurrence_count", 0),
                    "past": 0,
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
                    "label": "influence",
                    "recent": r.get("cooccurrence_count", 0),
                    "past": 0,
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
                    "recent": r.get("target_total_count", 0),
                    "past": 0,
                    "confidence_level": r.get("confidence_level", "low"),
                })
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Decision-impact insights unavailable: {e}")

        return out

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
                "line3": f"{raw['recent']} recent · {raw['past']} earlier",
            },
            "summary": f'"{raw["summary"]}" — {raw["label"]}. '
                       f'{raw["recent"]} recent mentions vs {raw["past"]} earlier.',
            "accentColor": ACCENTS[idx % len(ACCENTS)],
            "featured": idx == 0,
            "tags": [raw["label"]],
            "confidence": CONFIDENCE_MAP.get(raw["confidence_level"], 0.4),
            "detectedAt": detected_at,
            "seen": seen,
        }

    def list_summaries(self) -> list:
        """Return InsightSummary[], hiding resolved and still-snoozed insights."""
        statuses = db.get_insight_statuses(self.user_id)
        now = datetime.now(UTC)
        detected = now.isoformat()
        summaries = []
        idx = 0
        for raw in self._normalize():
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

    def _iris_read(self, raw: dict) -> str:
        return (
            f'I keep noticing "{raw["summary"]}". Lately it shows up as {raw["label"]} — '
            f'{raw["recent"]} times recently compared with {raw["past"]} earlier. '
            f'That shift is what caught my attention.'
        )

    def _evidence(self, raw: dict) -> list:
        return [
            {
                "kind": "comparison",
                "label": "Recent vs earlier mentions",
                "items": [
                    {"label": "Recent", "value": raw["recent"]},
                    {"label": "Earlier", "value": raw["past"]},
                ],
            },
            {
                "kind": "callout",
                "label": "Read",
                "value": str(raw["label"]),
                "sub": f"{raw['confidence_level']} confidence",
            },
        ]

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
                quotes.append({
                    "sourceDate": _iso(occurred)[:10],
                    "text": snippet,
                    "sourceKind": kind,
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
            "leverage": "Estimates directional influence — whether one pattern tends "
                        "to precede shifts in another.",
            "decision_impact": "Measures how other patterns shift in the period "
                               "following instances of an anchor pattern.",
        }.get(engine, "Derived from longitudinal pattern analysis over your entries.")
