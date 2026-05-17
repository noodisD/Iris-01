"""
Base Analytical Engine - Shared Protocol for All Analysis Engines

This abstract base class defines the contract that all analytical engines must follow:
- Initialization with user_id
- Evidence emission protocol
- Insight generation and standardization
- Confidence computation
- Insight suppression tracking

Engines that inherit from this base get consistent behavior for logging, evidence handling,
and metadata tracking. This eliminates boilerplate and ensures all engines speak the same language.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import logging

from .confidence import ConfidenceEngine
from .evidence import EvidenceEngine

logger = logging.getLogger(__name__)


class AnalyticalEngine(ABC):
    """
    Abstract base class for all analytical engines in IRIS.

    Each engine:
    1. Analyzes patterns using domain-specific logic
    2. Emits evidence that tracks its reasoning
    3. Produces insights with standardized shape
    4. Computes confidence using the central engine
    5. Stores results in domain-specific repositories

    Subclasses implement analyze_all() and analyze_X() methods.
    """

    def __init__(self, user_id: int):
        """Initialize with user context and shared engines."""
        self.user_id = user_id
        self.conf_engine = ConfidenceEngine()
        self.ev_engine = EvidenceEngine()
        self._evidence: List[Dict[str, Any]] = []

    def emit_evidence(self, ev_type: str, key: str, value: Any) -> None:
        """Buffer a piece of evidence for later persistence.

        Args:
            ev_type: Type of evidence (e.g. 'count', 'rate', 'delta')
            key: Name of the metric (e.g. 'recent_count')
            value: The measured value
        """
        self._evidence.append({"type": ev_type, "key": key, "value": value})

    def record_evidence(self, pattern_type: str, pattern_id: int,
                       engine_name: str) -> None:
        """Persist buffered evidence as an immutable snapshot."""
        if self._evidence:
            self.ev_engine.record_evidence(
                engine_name, pattern_type, pattern_id, self._evidence
            )
            self._evidence = []

    def clear_evidence(self) -> None:
        """Clear the evidence buffer."""
        self._evidence = []

    @abstractmethod
    def analyze_all(self) -> List[Dict[str, Any]]:
        """
        Analyze all applicable patterns for the user.

        Must return a list of insights, where each insight is a dict with:
        - Standard fields: id, engine_name, pattern_type, confidence_level, label
        - Engine-specific fields as needed

        Returns:
            List of insight dicts
        """
        pass

    def standardize_insight(self, insight: Dict[str, Any],
                           engine_name: str,
                           pattern_type: str) -> Dict[str, Any]:
        """
        Ensure an insight has all required metadata fields.

        Args:
            insight: The insight dict to standardize
            engine_name: Name of the engine that produced it
            pattern_type: Type of pattern (e.g. 'theme', 'tension')

        Returns:
            The insight with added metadata
        """
        if 'engine_name' not in insight:
            insight['engine_name'] = engine_name
        if 'pattern_type' not in insight:
            insight['pattern_type'] = pattern_type
        if 'confidence_level' not in insight:
            insight['confidence_level'] = 'unknown'
        return insight

    def format_for_context(self, max_items: int = 3) -> str:
        """
        Format top insights as narrative for LLM injection.

        Subclasses can override for domain-specific formatting.

        Args:
            max_items: Maximum number of items to include

        Returns:
            Narrative string or empty if no significant insights
        """
        return ""


class ThemeAnalysisEngine(AnalyticalEngine):
    """Base for engines that analyze theme-related patterns.

    Provides common utilities for theme-based analysis engines
    (Persistence, Trajectory, Resolution, etc.).
    """

    def get_all_themes(self):
        """Get all themes for the user. Subclass hook for repository access."""
        pass

    def get_theme_occurrences(self, theme_id: int):
        """Get occurrences for a theme. Subclass hook for repository access."""
        pass

    def get_theme(self, theme_id: int):
        """Get theme metadata. Subclass hook for repository access."""
        pass


class PairAnalysisEngine(AnalyticalEngine):
    """Base for engines that analyze pairs of patterns.

    Provides common utilities for pair-based analysis engines
    (Tension, Leverage, etc.).
    """

    def get_pair_analysis_window(self):
        """Get the time window for pair analysis. Subclass can override."""
        from datetime import datetime, timedelta
        from .constants import LEVERAGE_WINDOW_DAYS
        return datetime.now() - timedelta(days=LEVERAGE_WINDOW_DAYS)
