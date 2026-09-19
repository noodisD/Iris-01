"""The reader's second question, answered the simple way for tests that are
about something else.

Every finding is now checked for whether its quotes support it
(agent.observations.check_support). Tests of verification, merging and runs
fake the reading model; this lets their fakes answer that check with "every
quote supports", so they keep testing what they tested. The check itself —
denials, mentions, failures — is tested directly in test_claim_support.py.
"""

import json
import re

from agent.observations import SUPPORT_PROMPT


def is_support_check(system_prompt: str) -> bool:
    return system_prompt == SUPPORT_PROMPT


def every_quote_supports(messages) -> str:
    count = len(re.findall(r"^\[\d+\] ", messages[0]["content"], re.M))
    return json.dumps({"quotes": [{"i": i, "verdict": "supports"} for i in range(count)]})
