"""Content-derived identity of the personal interpretation and annotation pipeline."""

from .claim_checks import SYSTEM_PROMPT as CHECK_PROMPT, _Reply as CheckReply
from .dynamics import PersonalInsight, PersonalPattern, canonical_hash
from .lens_matching import MATCH_PROMPT, _Reply as LensReply
from .personal_insights import PROMPT as INSIGHT_PROMPT, _Reply as InsightReply
from .personal_patterns import SYSTEM_PROMPT as PATTERN_PROMPT, _Narrative


INTERPRETATION_VERSION = canonical_hash({
    "prompts": [PATTERN_PROMPT, INSIGHT_PROMPT, MATCH_PROMPT, CHECK_PROMPT],
    "schemas": [model.model_json_schema() for model in (
        _Narrative, InsightReply, LensReply, CheckReply, PersonalPattern, PersonalInsight)],
    "gates": "range-projection-v2;independent-occasions-v2;source-grounded-claims-v2;"
             "explicit-rivals-and-counterevidence-v2;lens-requirements-per-unit-v1",
})
