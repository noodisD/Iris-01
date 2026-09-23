"""Public application classes, loaded only when requested.

Importing a pure helper must not initialize the application, database, or API
clients. The public ``from agent import ...`` interface remains unchanged.
"""

from importlib import import_module
from typing import Any

__all__ = [
    "ConversationMemory",
    "Intelligence",
    "JournalEntry",
    "PersonalAICompanion",
]

__version__ = "0.1.0"

_EXPORTS = {
    "ConversationMemory": ".memory",
    "Intelligence": ".intelligence",
    "JournalEntry": ".journal_entry",
    "PersonalAICompanion": ".core",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value
