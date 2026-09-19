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
    # Two rules that were here compared a pair engine against a single theme,
    # and neither could hold. Leverage never emits "high", so "a dissipated
    # pattern cannot drive another" never fired. And a fade in decision impact
    # is a fade in the *target* after an anchor, while the rule set it against
    # the *anchor's* own trajectory — a different theme; even compared with the
    # right one, a dip after one kind of event does not contradict a rise
    # overall. Pair findings are grouped by pair now, so neither could be
    # matched anyway.
]
