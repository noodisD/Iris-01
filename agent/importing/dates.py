"""
Working out when an entry was written — or saying that we cannot.

`reflections.reflection_date` becomes `occurred_at` for every analytical window
in the system, so a wrong date here is not a small inaccuracy in one row. It
moves an entry into or out of the recent window, the baseline, the silence a
dissipation is measured against. And it does it silently: nothing downstream can
tell a guessed date from a known one.

So there is no fallback to today, and no fallback to the file's modification
time. A date is either read from something that actually states it, or the
entry is returned with `value=None` for a human to resolve. `probable` exists
for the genuinely ambiguous case — 03/04/2024 is either 3 April or 4 March, and
the note says so rather than picking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

DateSource = Literal[
    "json_field", "frontmatter", "csv_column", "filename",
    "heading", "path", "mtime", "user", "unknown",
]
Confidence = Literal["certain", "probable", "unknown"]


@dataclass(frozen=True)
class DateGuess:
    """A date, where it came from, and how much it should be trusted."""

    value: date | None = None
    source: DateSource = "unknown"
    confidence: Confidence = "unknown"
    raw: str | None = None
    note: str | None = None

    @property
    def known(self) -> bool:
        return self.value is not None


UNKNOWN = DateGuess()

_MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("january", "jan"), ("february", "feb"), ("march", "mar"),
            ("april", "apr"), ("may",), ("june", "jun"), ("july", "jul"),
            ("august", "aug"), ("september", "sep", "sept"), ("october", "oct"),
            ("november", "nov"), ("december", "dec"),
        ],
        start=1,
    )
    for m in names
}

# 2024-03-01, 2024/03/01, 2024.03.01, 2024_03_01
_ISO = re.compile(r"(?<!\d)(\d{4})[-_./](\d{1,2})[-_./](\d{1,2})(?!\d)")
# 20240301 — only when not part of a longer run of digits
_COMPACT = re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)")
# 03/04/2024 — day and month order is genuinely unknowable
_AMBIGUOUS = re.compile(r"(?<!\d)(\d{1,2})[-_./](\d{1,2})[-_./](\d{4})(?!\d)")
# "1 March 2024" / "1st March 2024"
_DAY_MONTH = re.compile(
    r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})(?!\d)", re.I
)
# "March 1, 2024" / "March 1st 2024"
_MONTH_DAY = re.compile(
    r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})(?!\d)", re.I
)


def _make(y: int, m: int, d: int) -> date | None:
    """A real calendar date, or None. Rejects 2024-13-40 and 2024-02-30 alike."""
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_date_text(text: str) -> DateGuess:
    """Read a date out of arbitrary text, most-certain pattern first."""
    if not text:
        return UNKNOWN

    if (m := _ISO.search(text)) and (d := _make(int(m[1]), int(m[2]), int(m[3]))):
        return DateGuess(d, "filename", "certain", raw=m[0])

    if (m := _COMPACT.search(text)) and (d := _make(int(m[1]), int(m[2]), int(m[3]))):
        return DateGuess(d, "filename", "certain", raw=m[0])

    for pattern, day_i, mon_i in ((_DAY_MONTH, 1, 2), (_MONTH_DAY, 2, 1)):
        m = pattern.search(text)
        if not m:
            continue
        month = _MONTHS.get(m[mon_i].lower().rstrip("."))
        if month and (d := _make(int(m[3]), month, int(m[day_i]))):
            return DateGuess(d, "heading", "certain", raw=m[0])

    if m := _AMBIGUOUS.search(text):
        a, b, year = int(m[1]), int(m[2]), int(m[3])
        # If one of the two cannot be a month, the reading is forced and certain.
        if a > 12 and (d := _make(year, b, a)):
            return DateGuess(d, "filename", "certain", raw=m[0])
        if b > 12 and (d := _make(year, a, b)):
            return DateGuess(d, "filename", "certain", raw=m[0])
        # Otherwise both readings are real. Take day-first (the majority of the
        # world, and what every European export uses) but say so, and never
        # let it through as certain.
        if d := _make(year, b, a):
            return DateGuess(
                d, "filename", "probable", raw=m[0],
                note=(f"{m[0]} could be {a} {date(year, b, 1):%B} or "
                      f"{b} {date(year, a, 1):%B} — read as day-first"),
            )
    return UNKNOWN


def parse_timestamp(value: str) -> DateGuess:
    """A date from an ISO 8601 instant, as structured exports carry.

    An instant is not a day until a zone is chosen. Where the string carries an
    offset it is honoured and the local day there is used; where it does not,
    the value is read as-is. Both are recorded as `json_field` so the choice is
    visible rather than assumed.
    """
    if not value:
        return UNKNOWN
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return parse_date_text(text)
    return DateGuess(dt.date(), "json_field", "certain", raw=str(value))


_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.S)
_FM_DATE_KEY = re.compile(
    r"^\s*(date|created|created_at|created time|day)\s*:\s*(.+?)\s*$", re.I | re.M
)


def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter, body). Frontmatter is '' when there is none."""
    m = _FRONTMATTER.match(text or "")
    return (m[1], text[m.end():]) if m else ("", text or "")


def from_frontmatter(text: str) -> DateGuess:
    """A date declared in YAML front matter — the most reliable source there is,
    because the exporting tool wrote it deliberately rather than incidentally."""
    fm, _ = split_frontmatter(text)
    if not fm:
        return UNKNOWN
    m = _FM_DATE_KEY.search(fm)
    if not m:
        return UNKNOWN
    guess = parse_timestamp(m[2].strip().strip("\"'"))
    if not guess.known:
        return UNKNOWN
    return DateGuess(guess.value, "frontmatter", guess.confidence, raw=m[2].strip())


def from_filename(name: str) -> DateGuess:
    """A date in a file's own name, e.g. `2024-03-01 Morning.md`."""
    guess = parse_date_text(name)
    return guess if guess.known else UNKNOWN


def from_path(rel_path: str) -> DateGuess:
    """A date spread across directories, e.g. `2024/03/01.md` or `2024/03-01.md`.

    Tried only after the filename alone has failed, and only when the parts join
    into a real date — so `notes/2024/ideas.md` stays unknown rather than
    becoming the first of some arbitrary month.
    """
    parts = [p for p in re.split(r"[\\/]", rel_path) if p]
    if len(parts) < 2:
        return UNKNOWN
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", parts[-1])
    joined = "-".join(parts[-3:-1] + [stem])
    guess = parse_date_text(joined)
    return DateGuess(guess.value, "path", guess.confidence, raw=joined) if guess.known else UNKNOWN


def best(*guesses: DateGuess) -> DateGuess:
    """The first usable guess, preferring certainty over order."""
    known = [g for g in guesses if g and g.known]
    if not known:
        return UNKNOWN
    for g in known:
        if g.confidence == "certain":
            return g
    return known[0]
