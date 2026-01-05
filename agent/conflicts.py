"""
Conflict Rules Registry

This module defines explicit logical contradictions between analytical engines.
Rules are defined as unordered sets of (engine, label) pairs to ensure 
matching is independent of discovery order.

Absence of a conflict rule implies coexistence is allowed.
"""

CONFLICT_RULES = [
    {
        "patterns": {
            ("resolution", "dissipated"),
            ("trajectory", "increasing")
        },
        "reason": "A pattern cannot be both absent recently and increasing in frequency."
    },
    {
        "patterns": {
            ("resolution", "dissipated"),
            ("trajectory", "emerging")
        },
        "reason": "A pattern cannot be both absent recently and newly emerging."
    },
    {
        "patterns": {
            ("resolution", "stabilized"),
            ("trajectory", "emerging")
        },
        "reason": "A stable pattern contradicts the definition of a newly emerging one."
    },
    {
        "patterns": {
            ("resolution", "dissipated"),
            ("leverage", "high") # Assuming 'high' is used or the label from engine
        },
        "reason": "A dissipated pattern cannot act as a current structural driver."
    },
    {
        "patterns": {
            ("decision_impact", "fade"),
            ("trajectory", "increasing")
        },
        "reason": "A post-anchor fade contradicts an overall increasing trend."
    }
]
