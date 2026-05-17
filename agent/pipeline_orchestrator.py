"""
Analysis Pipeline Orchestrator - Declarative Engine Composition

This module provides a clean abstraction for orchestrating analytical engines.
Instead of flat procedural code in core.py, engines are registered declaratively
and executed through composable stages (enrichment, analysis, filtering, gating).

The pipeline:
1. Registers engines with metadata
2. Executes all engines (serially or parallel)
3. Normalizes result shapes
4. Applies gates (filters) in sequence
5. Returns final insights ready for narrative formatting

Benefits:
- Engines are pluggable (add new engine = 1 register call)
- Gates are pluggable (add new gate = implement Gate interface)
- Execution strategy is decoupled (serial vs parallel)
- Easy to understand and trace the full analysis flow
- Tests can mock the pipeline or individual gates
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class Engine:
    """Metadata for a registered analytical engine."""
    name: str  # e.g. 'persistence', 'trajectory'
    callable: Callable  # The engine's analyze_all() method
    enabled_by_default: bool = True
    pattern_type: str = 'theme'  # What type of pattern does it analyze?


@dataclass
class Gate:
    """Metadata for a filtering gate."""
    name: str  # e.g. 'enablement', 'confidence', 'conflict'
    callable: Callable  # The gate's filter method
    order: int = 100  # Lower numbers run first


class AnalysisPipeline:
    """Orchestrates analytical engines and applies meta-control gates."""

    def __init__(self, user_id: int):
        """Initialize pipeline for a specific user."""
        self.user_id = user_id
        self.engines: Dict[str, Engine] = {}
        self.gates: List[Gate] = []
        self._insights: List[Dict[str, Any]] = []
        self._suppression_log: Dict[str, List[str]] = {}  # Track why insights were filtered

    def register_engine(self, name: str, callable: Callable,
                       enabled_by_default: bool = True,
                       pattern_type: str = 'theme') -> None:
        """Register an analytical engine for execution.

        Args:
            name: Engine name (must be unique)
            callable: Function returning list of insights
            enabled_by_default: Whether engine runs by default
            pattern_type: Type of pattern this engine analyzes
        """
        if name in self.engines:
            logger.warning(f"Engine '{name}' already registered, replacing")

        self.engines[name] = Engine(
            name=name,
            callable=callable,
            enabled_by_default=enabled_by_default,
            pattern_type=pattern_type
        )

    def register_gate(self, name: str, callable: Callable, order: int = 100) -> None:
        """Register a filtering gate to apply after analysis.

        Args:
            name: Gate name (e.g. 'confidence', 'conflict')
            callable: Function(insights, context) -> filtered_insights
            order: Execution order (lower = earlier)
        """
        gate = Gate(name=name, callable=callable, order=order)
        self.gates.append(gate)
        self.gates.sort(key=lambda g: g.order)  # Keep sorted

    def run(self, prefs: Optional[Dict[str, Any]] = None,
            parallel: bool = False) -> List[Dict[str, Any]]:
        """Execute the full pipeline.

        Args:
            prefs: User preferences to inform gating
            parallel: If True, run engines in parallel (requires thread pool)

        Returns:
            Final list of insights after all gates
        """
        self._insights = []
        self._suppression_log = {}

        # STAGE 1: Collect raw insights from all enabled engines
        try:
            self._run_engines(parallel)
        except Exception as e:
            logger.error(f"Error during engine execution: {e}")
            return []

        # STAGE 2: Normalize shapes
        self._normalize_insights()

        # STAGE 3: Apply gates in sequence
        try:
            self._apply_gates(prefs or {})
        except Exception as e:
            logger.error(f"Error during gating: {e}")
            return self._insights  # Return what we have

        return self._insights

    def _run_engines(self, parallel: bool = False) -> None:
        """Execute all registered engines."""
        for engine_name, engine in self.engines.items():
            if not engine.enabled_by_default:
                continue  # Skip disabled engines

            try:
                logger.debug(f"Running engine: {engine_name}")
                insights = engine.callable()

                # Tag each insight with its engine and map pattern_id based on engine
                for insight in insights:
                    if 'engine_name' not in insight:
                        insight['engine_name'] = engine_name
                    if 'pattern_type' not in insight:
                        insight['pattern_type'] = engine.pattern_type

                    # Map pattern_id from engine-specific fields
                    if 'pattern_id' not in insight:
                        if engine_name == 'persistence' and 'id' in insight:
                            insight['pattern_id'] = insight['id']
                        elif engine_name == 'trajectory' and 'theme_id' in insight:
                            insight['pattern_id'] = insight['theme_id']
                        elif engine_name == 'tension' and 'theme_a_id' in insight:
                            insight['pattern_id'] = insight['theme_a_id']
                        elif engine_name == 'resolution' and 'theme_id' in insight:
                            insight['pattern_id'] = insight['theme_id']
                        elif engine_name == 'leverage' and 'source_id' in insight:
                            insight['pattern_id'] = insight['source_id']
                        elif engine_name == 'decision_impact' and 'anchor_id' in insight:
                            insight['pattern_id'] = insight['anchor_id']

                self._insights.extend(insights)
            except Exception as e:
                logger.error(f"Engine '{engine_name}' failed: {e}")

    def _normalize_insights(self) -> None:
        """Ensure all insights have required metadata fields.

        After normalization, every insight has:
        - id or pattern_id (unique identifier)
        - engine_name (which engine produced it)
        - pattern_type (what kind of pattern)
        - confidence_level (unknown if not set)
        - label (human-readable summary)
        """
        for insight in self._insights:
            # Ensure id field (fallback to pattern_id)
            if 'id' not in insight and 'pattern_id' in insight:
                insight['id'] = insight['pattern_id']
            if 'id' not in insight and 'theme_id' in insight:
                insight['id'] = insight['theme_id']

            # Ensure confidence
            if 'confidence_level' not in insight:
                insight['confidence_level'] = 'unknown'

            # Ensure label
            if 'label' not in insight:
                insight['label'] = insight.get('summary', 'Insight')

    def _apply_gates(self, prefs: Dict[str, Any]) -> None:
        """Apply all registered gates in sequence."""
        context = {
            'user_id': self.user_id,
            'prefs': prefs,
            'suppression_log': self._suppression_log
        }

        for gate in self.gates:
            try:
                logger.debug(f"Applying gate: {gate.name}")
                self._insights = gate.callable(self._insights, context)
            except Exception as e:
                logger.error(f"Gate '{gate.name}' failed: {e}")

    def get_suppression_log(self) -> Dict[str, List[str]]:
        """Return log of why insights were suppressed at each gate."""
        return self._suppression_log

    def disable_engine(self, name: str) -> None:
        """Disable an engine without removing it."""
        if name in self.engines:
            self.engines[name].enabled_by_default = False

    def enable_engine(self, name: str) -> None:
        """Enable a previously disabled engine."""
        if name in self.engines:
            self.engines[name].enabled_by_default = True


# Standard gate implementations

def engine_enablement_gate(insights: List[Dict[str, Any]],
                          context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """GATE 1: Filter insights by user's enabled_engines preference.

    If prefs['enabled_engines'] is None, all engines are allowed.
    Otherwise, only insights from enabled engines pass through.
    """
    prefs = context.get('prefs', {})
    enabled = prefs.get('enabled_engines')  # None = all enabled

    if enabled is None:
        return insights

    filtered = []
    suppression_log = context['suppression_log']

    for insight in insights:
        engine_name = insight.get('engine_name', 'unknown')
        if engine_name in enabled:
            filtered.append(insight)
        else:
            if 'engine_disabled' not in suppression_log:
                suppression_log['engine_disabled'] = []
            suppression_log['engine_disabled'].append(
                f"{engine_name}: {insight.get('label', 'N/A')}"
            )

    return filtered


def confidence_gate(insights: List[Dict[str, Any]],
                   context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """GATE 2: Filter insights by confidence level.

    User can set min_confidence in prefs. Insights below that level are dropped.
    """
    prefs = context.get('prefs', {})
    min_conf = prefs.get('min_confidence', 'low')  # Default to low (allow most)

    # Confidence hierarchy
    levels = {'low': 0, 'medium': 1, 'high': 2}
    min_level = levels.get(min_conf, 0)

    filtered = []
    suppression_log = context['suppression_log']

    for insight in insights:
        conf = insight.get('confidence_level', 'low')
        conf_level = levels.get(conf, 0)

        if conf_level >= min_level:
            filtered.append(insight)
        else:
            if 'low_confidence' not in suppression_log:
                suppression_log['low_confidence'] = []
            suppression_log['low_confidence'].append(
                f"{insight.get('engine_name')}: {insight.get('label')} ({conf})"
            )

    return filtered


def budget_gate(insights: List[Dict[str, Any]],
               context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """GATE 4: Limit number of insights by user's max_items preference.

    Assumes insights are already ranked by priority.
    """
    prefs = context.get('prefs', {})
    max_items = prefs.get('max_items', 5)

    if len(insights) <= max_items:
        return insights

    suppression_log = context['suppression_log']
    if 'budget_cutoff' not in suppression_log:
        suppression_log['budget_cutoff'] = []

    for insight in insights[max_items:]:
        suppression_log['budget_cutoff'].append(
            f"{insight.get('engine_name')}: {insight.get('label')}"
        )

    return insights[:max_items]
