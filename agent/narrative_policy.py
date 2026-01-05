"""
Narrative Policy - Cognitive Firewall

Defines the forbidden lexicon and enforcement policies for IRIS narratives.
Strictly prevents causal, prescriptive, or interpretive language.
"""

import re

# Enforcement Mode: 'raise' (Dev) or 'silence' (Prod)
NARRATIVE_FAIL_MODE = "raise"

# Forbidden patterns using word boundaries (\b) and lemma variants
# Prevents: cause, caused, causing, should, recommend, meaning, implying, etc.
FORBIDDEN_PATTERNS = [
    r"\bcaus(e|ed|es|ing)\b",
    r"\bshould\b",
    r"\brecommend(s|ed|ing)?\b",
    r"\bmeans\b",
    r"\bimpl(y|ies|ied|ying)\b",
    r"\bindicate(s|d|ing)?\b",
    r"\bsuggest(s|ed|ing)?\b",
    r"\bfix(ed|es|ing)?\b",
    r"\bimprov(e|ed|es|ing)\b",
    r"\bsolv(e|ed|es|ing)\b",
    r"\bhelp(ed|s|ing)?\b",
    r"\btrigger(s|ed|ing)?\b",
    r"\ble(d|ad) to\b",
    r"\bresult(s|ed|ing) in\b",
    r"\bbecause\b",
    r"\bdue to\b"
]

# Compiled regex for efficiency
FORBIDDEN_REGEX = re.compile("|".join(FORBIDDEN_PATTERNS), re.IGNORECASE)
