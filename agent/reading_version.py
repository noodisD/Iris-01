"""Version the entire neutral reading, including independent contextual field checks."""

from .connections import FIELD_PROMPT, _FieldsIn
from .dynamics import canonical_hash
from .episodes import READER_VERSION


VERIFIED_READER_VERSION = canonical_hash({
    "extraction": READER_VERSION,
    "fieldPrompt": FIELD_PROMPT,
    "fieldSchema": _FieldsIn.model_json_schema(),
    "gate": "complete-field-matrix-v1;required-fail-optional-null-v1;original-paragraph-v1",
})
