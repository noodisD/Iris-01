"""IRIS Minimal Companion - Essential modules only"""

from .core import PersonalAICompanion
from .intelligence import Intelligence
from .memory import ConversationMemory
from .journal_entry import JournalEntry

__all__ = [
    "PersonalAICompanion",
    "Intelligence",
    "ConversationMemory",
    "JournalEntry",
]

__version__ = "0.1.0"
