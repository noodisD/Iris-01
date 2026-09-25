"""Markdown as words, for anything that reads an entry rather than displays it.

Stored journal text keeps its markers. Embeddings and models read this copy so
a marker is formatting, not part of the sentence. Plain entries are not passed
through here: an imported ``*`` stays a ``*``.
"""

from __future__ import annotations

import re

_WIKI_ALIAS = re.compile(r"\[\[([^\]|\n]+)\|([^\]\n]+)\]\]")
_WIKI = re.compile(r"\[\[([^\]\n]+)\]\]")
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)\n]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)\n]*\)")
_FENCE = re.compile(r"^[ \t]{0,3}```[^\n]*$", re.MULTILINE)
_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+")
_QUOTE = re.compile(r"^[ \t]{0,3}>[ \t]?")
_CHECKBOX = re.compile(r"^[ \t]{0,3}(?:[-*+]|\d+[.)])[ \t]+\[[ xX]\][ \t]+")
_LIST = re.compile(r"^[ \t]{0,3}(?:[-*+]|\d+[.)])[ \t]+")
_CODE = re.compile(r"`([^`\n]+)`")
_STRIKE = re.compile(r"~~(.+?)~~", re.DOTALL)
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.DOTALL)
_ITALIC = re.compile(r"(?<!\w)\*(.+?)\*(?!\w)|(?<!\w)_(.+?)_(?!\w)", re.DOTALL)
_LEFTOVER = re.compile(r"\*\*|__|~~|`")


def plain_text(md: str | None) -> str:
    """The words, without markdown markers.

    ``[[a|b]]`` becomes ``b`` and ``[t](u)`` becomes ``t``. Headings, quotes,
    lists and checkboxes lose their markers. Emphasis, strike and backticks
    lose theirs. A ``_`` inside a word is not a marker and stays.
    """
    if not md:
        return ""
    text = md.replace("\r\n", "\n").replace("\r", "\n")
    text = _WIKI_ALIAS.sub(r"\2", text)
    text = _WIKI.sub(r"\1", text)
    text = _IMAGE.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = _FENCE.sub("", text)
    lines: list[str] = []
    for line in text.split("\n"):
        stripped = _HEADING.sub("", line)
        while _QUOTE.match(stripped):
            stripped = _QUOTE.sub("", stripped, count=1)
        stripped = _CHECKBOX.sub("", stripped)
        stripped = _LIST.sub("", stripped)
        lines.append(stripped)
    text = "\n".join(lines)
    text = _CODE.sub(r"\1", text)
    text = _STRIKE.sub(r"\1", text)
    text = _BOLD.sub(lambda match: match.group(1) or match.group(2) or "", text)
    text = _ITALIC.sub(lambda match: match.group(1) or match.group(2) or "", text)
    return _LEFTOVER.sub("", text)


def for_model(content: str | None, content_format: str | None) -> str:
    """What a model or an embedding should read. Plain rows are unchanged."""
    text = content or ""
    if content_format == "markdown":
        return plain_text(text)
    return text
