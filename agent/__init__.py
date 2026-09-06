"""IRIS Minimal Companion - Essential modules only"""

from .core import PersonalAICompanion
from .intelligence import Intelligence
from .journal_entry import JournalEntry
from .memory import ConversationMemory

__all__ = [
    "ConversationMemory",
    "Intelligence",
    "JournalEntry",
    "PersonalAICompanion",
]

__version__ = "0.1.0"
