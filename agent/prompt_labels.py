"""
Words a journaling tool wrote around the owner's writing.

The earlier IRIS journal stored its evening entries as answers to fixed prompts
("What went well: ...", "Key insight: ..."), and the importer keeps those labels
so each answer still says what it answered. They are the tool's words rather
than the owner's, and identical in every entry of that format: embedded with the
writing, they pulled that tool's entries together by format instead of by what
they say, so a single week of them looked like a recurring theme (ADR-0014).

The text that is embedded leaves them out; the stored entry keeps them.
"""

import re

#: Every label the importer writes in front of the owner's words. A test holds
#: the importer to this list, so a new label cannot slip into embeddings.
PROMPT_LABELS: tuple[str, ...] = (
    "What went well", "What to improve", "Key insight", "Tomorrow's priorities",
    "Notes", "Ideas", "Goals", "Done",
)

# At the start of a line, or straight after the "Content: " marker: a
# reflection is embedded inside a one-line header ("Anchor: ... | Content: ..."),
# so the first label of an entry never starts a line of its own.
_LABEL_AT_LINE_START = re.compile(
    r"(?:^|(?<=Content: ))[ \t]*(?:"
    + "|".join(re.escape(label) for label in PROMPT_LABELS)
    + r"):[ \t]*",
    re.M,
)


def strip_prompt_labels(text: str) -> str:
    """The writing without the prompts in front of it."""
    return _LABEL_AT_LINE_START.sub("", text or "")
