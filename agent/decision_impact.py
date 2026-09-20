"""
Decision Impact Engine - Tracks Temporal Deltas Following Anchors

This engine performs post-hoc observational analysis only.
It does not imply causality, recommendation, or prediction.
All outputs are descriptive and retrospective.

The engine answers: "After pattern X appears, what other patterns tend to change shortly afterward?"
- Anchor: The event triggering the observation period.
- Baseline: Establish normal frequency before the anchor.
- Observation: Measure frequency in the window following the anchor.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from .confidence import ConfidenceEngine
from .timeutils import to_utc, utc_now
from .constants import (
    DECISION_IMPACT_BASELINE_DAYS,
    DECISION_IMPACT_BASELINE_EPSILON,
    DECISION_IMPACT_MIN_ANCHORS,
    DECISION_IMPACT_MIN_DATA_POINTS,
    DECISION_IMPACT_MIN_BASELINE_DAYS,
    DECISION_IMPACT_MIN_DELTA,
    DECISION_IMPACT_WINDOW_DAYS,
)

from .analysis_cache import remembered
from .database import db
from .evidence import EvidenceEngine

logger = logging.getLogger(__name__)


class DecisionImpactEngine:
    """
    Analyzes temporal sequences to identify shifts following anchor patterns.
    """

    # Class-level default so a partially constructed engine (the maths tests
    # build one with __new__ to keep the database out of reach) still resolves
    # it. Assigning in _observation_start shadows it per instance.
    _observation_start_cache: datetime | None = None

    def __init__(self, user_id: int):
        """Initialize the decision impact engine for a user."""
        self.user_id = user_id
        self.conf_engine = ConfidenceEngine()
        self.ev_engine = EvidenceEngine()
        self._evidence = []

    def emit_evidence(self, ev_type: str, key: str, value: Any):
        """Buffers evidence for later persistence."""
        self._evidence.append({"type": ev_type, "key": key, "value": value})

    def analyze_all_anchors(self, force_recompute: bool = False) -> list[dict]:
        """
        Performs a scan for all active patterns to find notable downstream shifts.

        Every anchor against every target: the slowest step in deciding what
        IRIS has noticed. The result is reused until the evidence or the hour
        changes (agent/analysis_cache.py). `force_recompute` bypasses that — it
        was accepted here before and did nothing.
        """
        return remembered("decision_impact", self.user_id, self._analyze_all_anchors,
                          force=force_recompute)

    def _analyze_all_anchors(self) -> list[dict]:
        # 1. Get active themes (those with enough occurrences)
        active_themes = self._get_candidate_anchors()
        if not active_themes:
            return []

        results = []
        # 2. Analyze each as an anchor
        for anchor in active_themes:
            impacts = self.analyze_anchor('theme', anchor['id'])
            results.extend(impacts)

        return results

    def analyze_anchor(self, anchor_type: str, anchor_id: int) -> list[dict]:
        """
        Computes shifts in all other patterns following instances of the anchor.
        """
        # 1. Get anchor timestamps
        anchors = self._get_anchor_events(anchor_type, anchor_id)
        if len(anchors) < DECISION_IMPACT_MIN_ANCHORS:
            return []

        # 2. Get all candidate targets (active themes)
        targets = db.get_themes(self.user_id)

        impacts = []
        for target in targets:
            if target['id'] == anchor_id:
                continue

            # 3. Compute Metrics
            result = self._calculate_impact(anchor_id, anchors, 'theme', target['id'])
            if result and result['effect_direction'] != 'none':
                result['anchor_id'] = anchor_id
                result['target_id'] = target['id']
                result['anchor_summary'] = db.get_theme_by_id(anchor_id)['summary']
                result['target_summary'] = target['summary']
                # NarrativeFormatter reads `summary` for the pattern name.
                result['summary'] = result['anchor_summary']
                impacts.append(result)

                # 4. Store in DB
                db.create_or_update_decision_impact(
                    anchor_type=anchor_type,
                    anchor_id=anchor_id,
                    target_type='theme',
                    target_id=target['id'],
                    effect_direction=result['effect_direction'],
                    delta_score=float(result['delta_score']),
                    anchor_count=result['anchor_count'],
                    target_count=result['target_total_count'],
                    confidence_level=result['confidence_level']
                )

        return impacts

    # --- Private Calculation Logic ---

    def _calculate_impact(self, anchor_id: int, anchor_timestamps: list[datetime],
                          target_type: str, target_id: int) -> dict | None:
        """
        Computes the aggregate delta across all anchor events.
        """
        # Get all target occurrences
        all_target_occs = self._get_all_occurrences(target_type, target_id)
        if len(all_target_occs) < DECISION_IMPACT_MIN_DATA_POINTS:
            return None

        # Only anchors whose follow-up window has fully elapsed can be judged.
        # The post-anchor rate divides by the whole window, so an anchor from
        # three days ago had three days of evidence scored over fourteen —
        # understating the rate roughly fivefold and making almost any recent
        # decision look like it had reduced the pattern. Right-censored anchors
        # are excluded rather than estimated from a partial window: with one or
        # two days elapsed the estimate is noise, and this system's contract is
        # to report evidence rather than to guess ahead of it.
        cutoff = utc_now() - timedelta(days=DECISION_IMPACT_WINDOW_DAYS)
        elapsed_anchors = [t for t in anchor_timestamps if t <= cutoff]

        # Several entries about one occasion are one episode, not several
        # confirmations. Ten entries written up at a single moment produced ten
        # supporting anchors, consistency 1.0 and high confidence from five
        # target events — the same five, scored ten times.
        #
        # The grouping is by day, matching how the rest of the system treats
        # simultaneity (leverage's _is_simultaneous, tension's shared-day
        # counting). A wider rule was tried and rejected: collapsing everything
        # closer together than the follow-up window also merged anchors ten days
        # apart, which are distinct occasions whose windows merely overlap in
        # part, and it silently disqualified any theme recurring faster than
        # once a fortnight from ever being an anchor.
        episodes: list[datetime] = []
        seen_days: set = set()
        for t in sorted(elapsed_anchors):
            day = t.date()
            if day not in seen_days:
                seen_days.add(day)
                episodes.append(t)

        if len(episodes) < DECISION_IMPACT_MIN_ANCHORS:
            return None

        # How far back the record actually goes. Without this the baseline rate
        # divided by a full 60 days whether or not 60 days had been observed, so
        # a new user logging steadily every day had their first weeks scored as
        # near-silence: a perfectly constant cadence came out as a 179% increase
        # at medium confidence, purely because the app had not existed yet.
        observation_start = self._observation_start()

        baseline_rates = []
        post_rates = []
        directions = []
        evaluated: list[datetime] = []
        seen_after: set = set()

        # For each episode, compute local delta
        for t in episodes:
            # Baseline window: [t - 60, t), clipped to what was observed.
            b_start = t - timedelta(days=DECISION_IMPACT_BASELINE_DAYS)
            if observation_start is not None:
                b_start = max(b_start, observation_start)

            observed_days = (t - b_start).total_seconds() / 86400.0
            if observed_days < DECISION_IMPACT_MIN_BASELINE_DAYS:
                # Nothing to compare this episode against.
                continue

            b_count = sum(1 for ts in all_target_occs if b_start <= ts < t)
            b_rate = b_count / observed_days

            # Post window: [t, t + 14]
            p_end = t + timedelta(days=DECISION_IMPACT_WINDOW_DAYS)
            in_window = [ts for ts in all_target_occs if t <= ts <= p_end]
            p_count = len(in_window)
            p_rate = p_count / DECISION_IMPACT_WINDOW_DAYS
            # Which target writing this episode actually saw. Episodes closer
            # together than the follow-up window share it, and shared evidence
            # is not independent confirmation.
            seen_after.update(in_window)

            baseline_rates.append(b_rate)
            post_rates.append(p_rate)
            evaluated.append(t)

            # Local direction
            if b_rate < DECISION_IMPACT_BASELINE_EPSILON:
                directions.append('emergence' if p_rate > 0 else 'none')
            elif p_rate < DECISION_IMPACT_BASELINE_EPSILON:
                directions.append('fade')
            elif (p_rate - b_rate) / b_rate >= DECISION_IMPACT_MIN_DELTA:
                directions.append('increase')
            elif (p_rate - b_rate) / b_rate <= -DECISION_IMPACT_MIN_DELTA:
                directions.append('decrease')
            else:
                directions.append('none')

        # Every episode was censored by insufficient observed baseline.
        if not baseline_rates:
            return None

        avg_baseline = np.mean(baseline_rates)
        avg_post = np.mean(post_rates)

        # Aggregate delta
        if avg_baseline < DECISION_IMPACT_BASELINE_EPSILON:
            delta = 1.0 if avg_post > 0 else 0.0
            direction = 'emergence' if avg_post > 0 else 'none'
        else:
            delta = (avg_post - avg_baseline) / avg_baseline
            if avg_post < DECISION_IMPACT_BASELINE_EPSILON:
                direction = 'fade'
            elif delta >= DECISION_IMPACT_MIN_DELTA:
                direction = 'increase'
            elif delta <= -DECISION_IMPACT_MIN_DELTA:
                direction = 'decrease'
            else:
                direction = 'none'

        if direction == 'none':
            return {"effect_direction": "none"}

        # Confidence Signal using central engine. The direction being reported
        # is passed in, so "direction agreement" is agreement with the sentence
        # on the card rather than with whichever local direction was commonest.
        self._evidence = [] # Clear buffer
        conf = self.conf_engine.compute_confidence('impact', anchor_id, evaluated, directions,
                                                   agrees_with=direction,
                                                   independent_support=len(seen_after))

        # Emit evidence
        self.emit_evidence('rate', 'avg_baseline_rate', avg_baseline)
        self.emit_evidence('rate', 'avg_post_rate', avg_post)
        self.emit_evidence('delta', 'delta_score', delta)
        self.emit_evidence('count', 'anchor_count', len(evaluated))
        self.emit_evidence('count', 'anchor_events_seen', len(anchor_timestamps))
        # A bundle is stored under the anchor alone, so it has to name the target
        # it describes.
        self.emit_evidence('count', 'target_id', target_id)

        # Deliberately not written to pattern_confidence: that registry is keyed
        # by (pattern_type, pattern_id) and cannot express an (anchor, target)
        # pair, so every target of the same anchor overwrote the last. The
        # authoritative value is on the decision_impacts row below, which is
        # keyed by both ends.

        # Store in evidence registry
        self.ev_engine.record_evidence(
            'impact', 'theme', anchor_id, self._evidence,
            related_pattern_id=target_id,
        )

        return {
            "effect_direction": direction,
            "delta_score": delta,
            "target_total_count": len(all_target_occs),
            # The cohort actually evaluated, not every anchor event on record.
            "anchor_count": len(evaluated),
            "confidence_level": conf['confidence_level'],
            "consistency_ratio": conf['consistency_score']
        }

    def _observation_start(self) -> datetime | None:
        """The earliest occurrence this user has on record, memoized.

        A proxy for when observation began. It is not the same thing as a
        deliberate record of observed days — a user can stop logging without
        stopping living — but it is a hard bound: nothing before this point was
        observed at all, so no baseline may be scored as if it had been.
        """
        if self._observation_start_cache is not None:
            return self._observation_start_cache

        earliest = None
        for theme in db.get_themes(self.user_id):
            first_seen = theme.get('first_seen_at')
            if not first_seen:
                continue
            dt = to_utc(first_seen)
            if dt and (earliest is None or dt < earliest):
                earliest = dt

        self._observation_start_cache = earliest
        return earliest

    # --- Helpers ---

    def _get_candidate_anchors(self) -> list[dict]:
        """Returns themes with enough data to be anchors."""
        all_themes = db.get_themes(self.user_id)
        # 1. Min count filter
        active = [t for t in all_themes if t['occurrence_count'] >= DECISION_IMPACT_MIN_ANCHORS]

        # 2. Dissipation filter (don't anchor on dead patterns)
        #
        # This required 'high', which a freshly computed dissipation cannot
        # reach: the label needs RESOLUTION_RECENT_DAYS (21) of silence, and the
        # confidence engine's recency term is exp(-21/30) = 0.4966, just under
        # the 0.5 the 'high' branch demands. The filter was therefore dead and
        # dead patterns went on being anchors.
        #
        # Medium is the right bar here regardless of that arithmetic. This is not
        # a claim shown to anyone — it is a decision about what to spend an
        # O(themes^2) scan on, and a medium-confidence dissipation is already
        # good enough reason not to anchor on a theme.
        from .resolution import ResolutionEngine
        res_engine = ResolutionEngine(self.user_id)

        refined = []
        for t in active:
            res = res_engine.analyze_theme(t['id'])
            if (res['resolution_label'] == 'dissipated'
                    and res['confidence_level'] in ('medium', 'high')):
                continue
            refined.append(t)
        return refined

    def _get_anchor_events(self, a_type: str, a_id: int) -> list[datetime]:
        """Returns timestamps of anchor occurrences."""
        if a_type != 'theme': return []
        occs = db.get_theme_occurrences(a_id)
        times = []
        for o in occs:
            dt = to_utc(o['occurred_at'])
            times.append(dt)
        return sorted(times)

    def _get_all_occurrences(self, t_type: str, t_id: int) -> list[datetime]:
        """Returns all timestamps for a target theme."""
        if t_type != 'theme': return []
        occs = db.get_theme_occurrences(t_id)
        times = []
        for o in occs:
            times.append(to_utc(o['occurred_at']))
        return sorted(times)
