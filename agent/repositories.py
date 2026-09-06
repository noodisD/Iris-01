"""
Repository Layer - Domain-Specific Data Access

Extracts domain logic from the monolithic Database class by providing
domain-organized interfaces. Each repository delegates directly to the
Database singleton, creating seams where the backend can be adapted or
tested independently.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class Repository:
    """Base repository providing common database access patterns."""

    def __init__(self, db):
        """Initialize with a reference to the database singleton."""
        self.db = db


class UserRepository(Repository):
    """Manages user accounts and authentication."""

    def create_user(self, username: str, password: str) -> int:
        return self.db.create_user(username, password)

    def get_user(self, username: str) -> dict:
        return self.db.get_user(username)

    def verify_user(self, username: str, password: str) -> dict:
        return self.db.verify_user(username, password)


class JournalRepository(Repository):
    """Manages journal entries, reflections, and chat history."""

    def create_entry(self, user_id: int, raw_text: str, wellbeing_data: dict) -> int:
        return self.db.create_journal_entry(user_id, raw_text, wellbeing_data)

    def get_entry(self, entry_id: int) -> str:
        return self.db.get_journal_entry_content(entry_id)

    def get_recent_entries(self, user_id: int, limit: int = 3) -> list:
        return self.db.get_recent_journal_entries(user_id, limit)

    def get_entry_count(self, user_id: int) -> int:
        return self.db.get_entry_count(user_id)

    def create_reflection(self, user_id: int, content: str, reflection_date=None,
                         mood: str = None, energy: int = None, clarity: int = None,
                         tags: dict = None) -> int:
        return self.db.create_reflection(user_id, content, reflection_date, mood, energy, clarity, tags)

    def get_reflections(self, user_id: int, limit: int = 30) -> list:
        return self.db.get_reflections(user_id, limit)

    def get_reflection(self, reflection_id: int) -> dict:
        return self.db.get_reflection(reflection_id)

    def update_reflection(self, reflection_id: int, **updates) -> bool:
        return self.db.update_reflection(reflection_id, **updates)

    def delete_reflection(self, reflection_id: int) -> bool:
        return self.db.delete_reflection(reflection_id)

    def create_conversation_message(self, user_id: int, session_id: str, role: str, content: str) -> int:
        return self.db.create_conversation_message(user_id, session_id, role, content)

    def get_chat_history(self, user_id: int, limit: int = 50) -> list:
        return self.db.get_chat_history(user_id, limit)


class HabitRepository(Repository):
    """Manages habits and habit tracking."""

    def create_habit(self, user_id: int, name: str, description: str = None,
                    frequency_type: str = 'daily', habit_type: str = 'completion',
                    weekly_target: float = 0, tracking_metric: str = 'completion',
                    category: str = 'general') -> int:
        # These used to be (categories, target_frequency) passed positionally
        # into (frequency_type, habit_type) — both CHECK-constrained columns —
        # so any caller would have written a list into a VARCHAR or violated
        # the constraint.
        return self.db.create_habit(user_id, name, description, frequency_type,
                                    habit_type, weekly_target, tracking_metric, category)

    def get_habits(self, user_id: int, active_only: bool = True) -> list:
        return self.db.get_habits(user_id, active_only)

    def get_habit(self, habit_id: int) -> dict:
        return self.db.get_habit(habit_id)

    def update_habit(self, habit_id: int, **updates) -> bool:
        return self.db.update_habit(habit_id, **updates)

    def delete_habit(self, habit_id: int) -> bool:
        return self.db.delete_habit(habit_id)

    def log_completion(self, habit_id: int, completion_date, value: float = 1.0, notes: str = None) -> int:
        return self.db.log_habit_completion(habit_id, completion_date, value, notes)

    def log_skip(self, habit_id: int, skip_date, reason: str = None) -> int:
        return self.db.log_habit_skip(habit_id, skip_date, reason)

    def get_completions(self, habit_id: int, start_date=None, end_date=None) -> list:
        return self.db.get_habit_completions(habit_id, start_date, end_date)


class EmbeddingRepository(Repository):
    """Manages embeddings and processing status."""

    def add_embedding(self, source_type: str, source_id: int, model_name: str, vector: list):
        return self.db.add_embedding(source_type, source_id, model_name, vector)

    def search_similar(self, user_id: int, query_vector: list, n_results: int = 5) -> list:
        return self.db.search_similar_embeddings(user_id, query_vector, n_results)

    def update_processing_status(self, source_type: str, source_id: int, status: str):
        return self.db.update_processing_status(source_type, source_id, status)

    def get_items_to_process(self, source_type: str, status: str = 'pending', limit: int = 10,
                             source_id: int = None) -> list:
        return self.db.get_items_to_process(source_type, status, limit, source_id)

    def get_unassigned_embeddings(self, user_id: int) -> list:
        return self.db.get_unassigned_embeddings(user_id)

    def get_content_for_source(self, source_type: str, source_id: int) -> str:
        return self.db.get_content_for_source(source_type, source_id)


class ThemeRepository(Repository):
    """Manages themes and their metadata."""

    def create_theme(self, user_id: int, centroid_embedding: list, summary: str,
                    first_seen_at: str = None, last_seen_at: str = None,
                    occurrence_count: int = 1, primary_example: str = None) -> int:
        return self.db.create_theme(user_id, centroid_embedding, summary,
                                    first_seen_at or '', last_seen_at or '', occurrence_count)

    def get_all_themes(self, user_id: int) -> list:
        return self.db.get_themes(user_id)

    def get_theme(self, theme_id: int) -> dict:
        return self.db.get_theme_by_id(theme_id)

    def update_stats(self, theme_id: int, last_seen_at: str):
        return self.db.update_theme_stats(theme_id, last_seen_at)

    def add_occurrence(self, theme_id: int, source_type: str, source_id: int,
                       snippet: str = None, similarity_score: float = None, occurred_at: str = None):
        return self.db.add_theme_occurrence(theme_id, source_type, source_id, snippet,
                                           similarity_score, occurred_at)

    def get_occurrences(self, theme_id: int) -> list:
        return self.db.get_theme_occurrences(theme_id)

    def get_theme_pairs(self, user_id: int) -> list:
        return self.db.get_theme_pairs(user_id)

    def get_pair_occurrences(self, theme_a_id: int, theme_b_id: int) -> list:
        return self.db.get_theme_pair_occurrences(theme_a_id, theme_b_id)


class TrajectoryRepository(Repository):
    """Manages theme trajectory analysis."""

    def create_or_update(self, theme_id: int, trajectory_label: str,
                        trend_score: float, recent_count: int, past_count: int,
                        confidence_level: str, data_points_count: int):
        return self.db.create_theme_trajectory(theme_id, trajectory_label,
                                              trend_score, recent_count, past_count,
                                              confidence_level, data_points_count)

    def get_trajectory(self, theme_id: int) -> dict:
        return self.db.get_theme_trajectory(theme_id)

    def update_trajectory(self, theme_id: int, trajectory_label: str, analysis_date: str = None,
                         slope: float = None, r_squared: float = None, trend_score: float = None, **kwargs):
        if slope is not None:
            return self.db.update_theme_trajectory(theme_id, trajectory_label, analysis_date,
                                                  slope, r_squared)
        else:
            return self.db.update_theme_trajectory(theme_id, trajectory_label, analysis_date,
                                                  trend_score or 0, 0)

    def get_all_trajectories(self, user_id: int) -> list:
        return self.db.get_all_theme_trajectories(user_id)


class TensionRepository(Repository):
    """Manages tension analysis between theme pairs."""

    def get_theme_pairs(self, user_id: int) -> list:
        return self.db.get_theme_pairs(user_id)

    def get_pair_occurrences(self, theme_a_id: int, theme_b_id: int) -> list:
        return self.db.get_theme_pair_occurrences(theme_a_id, theme_b_id)

    def create_or_update(self, theme_a_id: int, theme_b_id: int, cooccurrence_count: int,
                        recent_cooccurrence_count: int, past_cooccurrence_count: int,
                        divergence_score: float, stability_score: float,
                        tension_label: str, confidence_level: str):
        return self.db.create_or_update_tension(theme_a_id, theme_b_id, cooccurrence_count,
                                               recent_cooccurrence_count, past_cooccurrence_count,
                                               divergence_score, stability_score,
                                               tension_label, confidence_level)

    def get_all_tensions(self, user_id: int) -> list:
        return self.db.get_all_tensions(user_id)

    def get_significant_tensions(self, user_id: int) -> list:
        return self.db.get_significant_tensions(user_id)

    def invalidate_for_theme(self, theme_id: int):
        return self.db.invalidate_tension(theme_id)


class ResolutionRepository(Repository):
    """Manages resolution analysis."""

    def create_or_update(self, pattern_type: str, pattern_id: int, resolution_label: str,
                        attenuation_score: float, confidence_level: str,
                        recent_count: int, past_count: int):
        return self.db.create_or_update_resolution(pattern_type, pattern_id, resolution_label,
                                                  attenuation_score, confidence_level,
                                                  recent_count, past_count)

    def get_resolution(self, pattern_type: str, pattern_id: int) -> dict:
        return self.db.get_resolution(pattern_type, pattern_id)

    def get_all_resolutions(self, user_id: int) -> list:
        return self.db.get_all_resolutions(user_id)

    def invalidate(self, pattern_type: str, pattern_id: int):
        return self.db.invalidate_resolution(pattern_type, pattern_id)


class LeverageRepository(Repository):
    """Manages leverage analysis."""

    def create_or_update_pair(self, source_type: str, source_id: int,
                             target_type: str, target_id: int,
                             influence_score: float, directional_lift: float,
                             cooccurrence_count: int, confidence_level: str):
        return self.db.create_or_update_leverage_pair(source_type, source_id,
                                                     target_type, target_id,
                                                     influence_score, directional_lift,
                                                     cooccurrence_count, confidence_level)

    def get_targets(self, source_type: str, source_id: int) -> list:
        return self.db.get_leverage_targets(source_type, source_id)

    def get_high_leverage_sources(self, user_id: int, min_confidence: str = 'medium') -> list:
        return self.db.get_high_leverage_sources(user_id, min_confidence)

    def invalidate_for_source(self, source_type: str, source_id: int):
        return self.db.invalidate_leverage_for_source(source_type, source_id)


class DecisionImpactRepository(Repository):
    """Manages decision impact analysis."""

    def create_or_update(self, anchor_type: str, anchor_id: int,
                        target_type: str, target_id: int,
                        effect_direction: str, delta_score: float,
                        anchor_count: int, target_count: int,
                        confidence_level: str):
        return self.db.create_or_update_decision_impact(anchor_type, anchor_id,
                                                       target_type, target_id,
                                                       effect_direction, delta_score,
                                                       anchor_count, target_count,
                                                       confidence_level)

    def get_impacts_for_anchor(self, anchor_type: str, anchor_id: int) -> list:
        return self.db.get_decision_impacts_for_anchor(anchor_type, anchor_id)

    def get_significant_impacts(self, user_id: int, min_confidence: str = 'medium') -> list:
        return self.db.get_significant_decision_impacts(user_id, min_confidence)

    def invalidate_impacts(self, pattern_type: str, pattern_id: int):
        return self.db.invalidate_decision_impacts(pattern_type, pattern_id)


class ConfidenceRepository(Repository):
    """Manages confidence scores."""

    def create_or_update(self, pattern_type: str, pattern_id: int,
                        confidence_level: str, confidence_score: float,
                        data_points_count: int, time_coverage_days: int,
                        consistency_score: float, recency_score: float):
        return self.db.create_or_update_confidence(pattern_type, pattern_id,
                                                  confidence_level, confidence_score,
                                                  data_points_count, time_coverage_days,
                                                  consistency_score, recency_score)

    def get_confidence(self, pattern_type: str, pattern_id: int) -> dict:
        return self.db.get_confidence(pattern_type, pattern_id)

    def invalidate(self, pattern_type: str, pattern_id: int):
        return self.db.invalidate_pattern_confidence(pattern_type, pattern_id)


class EvidenceRepository(Repository):
    """Manages evidence records and bundles."""

    def add_records(self, records: list):
        return self.db.add_evidence_records(records)

    def get_latest_bundle(self, pattern_type: str, pattern_id: int, engine_name: str = None) -> list:
        return self.db.get_latest_evidence_bundle(pattern_type, pattern_id, engine_name)


class PrioritizationRepository(Repository):
    """Manages insight prioritization."""

    def create_or_update(self, insight_id: str, engine_name: str,
                        priority_score: float, reasoning: str = None):
        return self.db.create_or_update_insight_priority(insight_id, engine_name,
                                                        priority_score, reasoning)

    def get_priority(self, engine_name: str, pattern_type: str, pattern_id: int) -> dict:
        return self.db.get_insight_priority(engine_name, pattern_type, pattern_id)


class PreferenceRepository(Repository):
    """Manages user preferences."""

    def get_preferences(self, user_id: int) -> dict:
        return self.db.get_preferences(user_id)

    def update_preference(self, user_id: int, key: str, value: Any):
        return self.db.update_preference(user_id, key, value)

    def reset_preferences(self, user_id: int):
        return self.db.reset_preferences(user_id)


# Factory function to initialize all repositories with a database instance
def initialize_repositories(db):
    """Initialize all repository instances."""
    repositories = {
        'users': UserRepository(db),
        'journals': JournalRepository(db),
        'habits': HabitRepository(db),
        'embeddings': EmbeddingRepository(db),
        'themes': ThemeRepository(db),
        'trajectories': TrajectoryRepository(db),
        'tensions': TensionRepository(db),
        'resolutions': ResolutionRepository(db),
        'leverage': LeverageRepository(db),
        'decision_impacts': DecisionImpactRepository(db),
        'confidence': ConfidenceRepository(db),
        'evidence': EvidenceRepository(db),
        'priorities': PrioritizationRepository(db),
        'preferences': PreferenceRepository(db),
    }
    return repositories
