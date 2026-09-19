"""
Reading an export whose format we were not told.

The owner's journals live in some app — Notion, Obsidian, Day One, a folder of
text files — and which one is not known in advance. So rather than one parser,
this is a small registry of adapters that each say how well they recognise a
bundle, and the best score wins. Detection is advisory: the result is always
shown for review before anything is committed, and the adapter can be overridden
by hand.

An adapter's whole job is to turn files into candidate entries. It decides
nothing about what happens next, touches no database, and makes no network call.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Protocol
from collections.abc import Iterator

from .bundle import Bundle, BundleFile
from .dates import UNKNOWN, DateGuess, best, from_filename, from_frontmatter, \
    from_path, parse_date_text, parse_timestamp, split_frontmatter

logger = logging.getLogger(__name__)

MARKDOWN_SUFFIXES = {".md", ".markdown", ".txt", ".text"}


@dataclass
class ParsedEntry:
    """One candidate entry. Nothing here has been written anywhere yet."""

    content: str
    date: DateGuess = UNKNOWN
    #: Typed values the source recorded, with their own scales — mood, energy,
    #: sleep, stress and the rest. Prose is content; these are measurements.
    metrics: dict | None = None
    title: str | None = None
    source_path: str = ""
    tags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: Why this looks written by an assistant rather than the owner, if it does.
    #: Such entries are staged excluded: an earlier AI's conclusions imported as
    #: the owner's journal would come back out of the engines as "patterns".
    likely_generated: str | None = None


class SourceAdapter(Protocol):
    name: str
    label: str
    description: str

    def sniff(self, bundle: Bundle) -> float: ...
    def parse(self, bundle: Bundle) -> Iterator[ParsedEntry]: ...


# --- helpers ---------------------------------------------------------------

_NOTION_ID = re.compile(r"\s+[0-9a-f]{32}(?=\.|$)")
# Notion writes a property block under the title: "Created: March 1, 2024".
_PROPERTY_LINE = re.compile(r"^([A-Z][A-Za-z ]{2,24}):\s*(.*)$")
# A heading that carries a date, which is how a single-file journal separates
# entries: "# 2024-03-01", "## Monday, 4 March 2024".
_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


# Signals that a note was produced by an assistant rather than written by the
# owner. Taken from the one real case seen so far — an earlier companion that
# wrote "Breakthrough", "Session" and "Query Results" notes into the owner's
# vault with dates in their filenames. Heuristic, and deliberately narrow: each
# signal is something a person does not write in their own journal. A hit only
# changes the default (excluded, with the reason shown); it can be overridden.
_GENERATED_FM_KEYS = {"breakthrough_id", "breakthrough_count", "session_id",
                      "date_queried", "time_queried", "result_count"}
_GENERATED_HEADING = re.compile(
    r"^#{1,4}\s+(breakthrough/realization detected|session insights|"
    r"query results:|psychological dimensions)", re.I | re.M)
_GENERATED_DIR = re.compile(
    r"(?i)(^|/)(breakthroughs|ai companion sessions|query results|messenger insights)(/|$)")


def generated_reason(raw: str, rel_path: str = "") -> str | None:
    """Why this looks like an assistant's output rather than the owner's writing."""
    fm, _ = split_frontmatter(raw or "")
    keys = set(re.findall(r"^([A-Za-z_][\w-]*):", fm, re.M)) & _GENERATED_FM_KEYS
    if keys:
        return ("This looks written by an assistant, not by you "
                f"(its metadata has {', '.join(sorted(keys))}).")
    if m := _GENERATED_HEADING.search(raw or ""):
        return f"This looks like an assistant's summary (heading “{m.group(1)}”)."
    if _GENERATED_DIR.search(rel_path or ""):
        return "This sits in a folder of assistant-generated notes."
    return None


def _clean(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", (text or "").strip())


def _is_meaningful(text: str) -> bool:
    """Enough words to be an entry rather than a stub or an index page."""
    return len(text.split()) >= 3


# --- adapters --------------------------------------------------------------

class DayOneAdapter:
    name = "dayone"
    label = "Day One export"
    description = "A Day One JSON export, with creationDate on every entry."

    def _payloads(self, bundle: Bundle) -> Iterator[tuple[str, dict]]:
        for f in bundle.files({".json"}):
            try:
                data = json.loads(bundle.read_text(f.rel_path))
            except (ValueError, OSError):
                continue
            if isinstance(data, dict) and isinstance(data.get("entries"), list):
                yield f.rel_path, data

    def sniff(self, bundle: Bundle) -> float:
        for _, data in self._payloads(bundle):
            entries = data["entries"]
            if entries and any(
                isinstance(e, dict) and "creationDate" in e for e in entries[:20]
            ):
                return 0.97
        return 0.0

    def parse(self, bundle: Bundle) -> Iterator[ParsedEntry]:
        for rel, data in self._payloads(bundle):
            for i, entry in enumerate(data["entries"]):
                if not isinstance(entry, dict):
                    continue
                text = _clean(entry.get("text") or entry.get("richText") or "")
                if not text:
                    continue
                tags = [t for t in (entry.get("tags") or []) if isinstance(t, str)]
                warnings = []
                if entry.get("audios"):
                    warnings.append("entry had attached audio, which is not imported")
                yield ParsedEntry(
                    content=text,
                    date=parse_timestamp(entry.get("creationDate", "")),
                    title=None,
                    source_path=f"{rel}#{entry.get('uuid', i)}",
                    tags=tags,
                    warnings=warnings,
                )


class NotionAdapter:
    name = "notion"
    label = "Notion export"
    description = "Markdown exported from Notion — page ids in the filenames."

    def _pages(self, bundle: Bundle) -> list[BundleFile]:
        return [f for f in bundle.files(MARKDOWN_SUFFIXES) if _NOTION_ID.search(f.stem)]

    def sniff(self, bundle: Bundle) -> float:
        md = bundle.files(MARKDOWN_SUFFIXES)
        pages = self._pages(bundle)
        # No page ids means this is not a Notion export, whatever else it is.
        # The share only refines confidence once at least one is present; using
        # it as a floor claimed every folder of markdown ever written.
        if not md or not pages:
            return 0.0
        # The 32-hex id Notion appends is unique to it and will not occur by
        # accident, so the share of files carrying one is a strong signal.
        return min(0.96, 0.55 + 0.45 * (len(pages) / len(md)))

    def parse(self, bundle: Bundle) -> Iterator[ParsedEntry]:
        for f in self._pages(bundle) or bundle.files(MARKDOWN_SUFFIXES):
            raw = bundle.read_text(f.rel_path)
            _, body = split_frontmatter(raw)
            lines = body.split("\n")

            title = None
            if lines and lines[0].startswith("# "):
                title = lines[0][2:].strip()
                lines = lines[1:]

            # Notion puts a block of "Key: value" properties directly under the
            # title. They are metadata, not writing, so they are lifted out of
            # the content — and one of them is usually the date.
            properties: dict[str, str] = {}
            while lines and (not lines[0].strip() or _PROPERTY_LINE.match(lines[0])):
                line = lines.pop(0)
                if m := _PROPERTY_LINE.match(line):
                    properties[m[1].strip().lower()] = m[2].strip()
                elif properties:
                    break

            content = _clean("\n".join(lines))
            if not _is_meaningful(content):
                continue

            declared = next(
                (properties[k] for k in ("created", "created time", "date", "day")
                 if properties.get(k)),
                "",
            )
            guess = parse_timestamp(declared) if declared else UNKNOWN
            if guess.known:
                guess = DateGuess(guess.value, "frontmatter", guess.confidence, raw=declared)

            clean_name = _NOTION_ID.sub("", f.stem)
            yield ParsedEntry(
                likely_generated=generated_reason(raw, f.rel_path),
                content=content,
                date=best(guess, from_frontmatter(raw), from_filename(clean_name),
                          from_path(f.rel_path)),
                title=title or clean_name or None,
                source_path=f.rel_path,
                tags=[t.strip() for t in properties.get("tags", "").split(",") if t.strip()],
            )


class DatedFilesAdapter:
    name = "dated_files"
    label = "One file per entry"
    description = "A folder of notes whose filenames or paths carry the date."

    def _dated(self, bundle: Bundle) -> list[tuple[BundleFile, DateGuess]]:
        out = []
        for f in bundle.files(MARKDOWN_SUFFIXES):
            guess = best(from_filename(f.stem), from_path(f.rel_path))
            out.append((f, guess))
        return out

    def sniff(self, bundle: Bundle) -> float:
        pairs = self._dated(bundle)
        if len(pairs) < 2:
            return 0.0
        share = sum(1 for _, g in pairs if g.known) / len(pairs)
        return 0.9 * share if share >= 0.6 else 0.0

    def parse(self, bundle: Bundle) -> Iterator[ParsedEntry]:
        for f, guess in self._dated(bundle):
            raw = bundle.read_text(f.rel_path)
            fm_date = from_frontmatter(raw)
            _, body = split_frontmatter(raw)
            content = _clean(body)
            if not _is_meaningful(content):
                continue
            yield ParsedEntry(
                content=content,
                date=best(fm_date, guess),
                title=None,
                source_path=f.rel_path,
                likely_generated=generated_reason(raw, f.rel_path),
            )


class SingleFileAdapter:
    name = "single_file"
    label = "One file, entries under date headings"
    description = "A single document where each entry starts at a dated heading."

    def _candidates(self, bundle: Bundle) -> list[BundleFile]:
        return [f for f in bundle.files(MARKDOWN_SUFFIXES) if f.size > 400]

    def _sections(self, text: str) -> list[tuple[DateGuess, str, str]]:
        sections: list[tuple[DateGuess, str, str]] = []
        current: tuple[DateGuess, str] | None = None
        buf: list[str] = []
        for line in text.split("\n"):
            m = _HEADING.match(line)
            guess = parse_date_text(m[2]) if m else UNKNOWN
            if m and guess.known:
                if current:
                    sections.append((current[0], current[1], "\n".join(buf)))
                current, buf = (guess, m[2]), []
            elif current:
                buf.append(line)
        if current:
            sections.append((current[0], current[1], "\n".join(buf)))
        return sections

    def sniff(self, bundle: Bundle) -> float:
        files = self._candidates(bundle)
        if len(files) != 1:
            return 0.0
        found = self._sections(bundle.read_text(files[0].rel_path))
        return 0.88 if len(found) >= 3 else 0.0

    def parse(self, bundle: Bundle) -> Iterator[ParsedEntry]:
        for f in self._candidates(bundle):
            for guess, heading, body in self._sections(bundle.read_text(f.rel_path)):
                content = _clean(body)
                if not _is_meaningful(content):
                    continue
                yield ParsedEntry(
                    content=content,
                    date=guess,
                    title=heading,
                    source_path=f"{f.rel_path}#{guess.value}",
                )


class CsvAdapter:
    name = "csv_table"
    label = "CSV table"
    description = "A spreadsheet export with a date column and a text column."

    def _analyse(self, bundle: Bundle):
        for f in bundle.files({".csv"}):
            try:
                rows = list(csv.DictReader(io.StringIO(bundle.read_text(f.rel_path))))
            except (ValueError, OSError):
                continue
            if not rows or not rows[0]:
                continue
            columns = [c for c in rows[0] if c]
            sample = rows[:50]
            date_col = next(
                (c for c in columns
                 if sum(1 for r in sample if parse_date_text(str(r.get(c) or "")).known)
                 >= 0.8 * len(sample)),
                None,
            )
            text_col = max(
                columns,
                key=lambda c: sum(len(str(r.get(c) or "")) for r in sample) / len(sample),
                default=None,
            )
            if date_col and text_col and text_col != date_col:
                avg = sum(len(str(r.get(text_col) or "")) for r in sample) / len(sample)
                if avg >= 120:
                    yield f, rows, date_col, text_col

    def sniff(self, bundle: Bundle) -> float:
        return 0.8 if next(self._analyse(bundle), None) else 0.0

    def parse(self, bundle: Bundle) -> Iterator[ParsedEntry]:
        for f, rows, date_col, text_col in self._analyse(bundle):
            for i, row in enumerate(rows):
                content = _clean(str(row.get(text_col) or ""))
                if not _is_meaningful(content):
                    continue
                yield ParsedEntry(
                    content=content,
                    date=parse_timestamp(str(row.get(date_col) or "")),
                    title=str(row.get("Name") or row.get("Title") or "") or None,
                    source_path=f"{f.rel_path}#{i + 2}",
                )


class PlainFilesAdapter:
    name = "plain_files"
    label = "Plain files (dates need checking)"
    description = "Every text file becomes one entry; dates are read where possible."

    def sniff(self, bundle: Bundle) -> float:
        # The floor. Always applicable, always beaten by anything that actually
        # recognises the format — so it is what a genuinely unknown export gets,
        # rather than a failure.
        return 0.1 if bundle.files(MARKDOWN_SUFFIXES) else 0.0

    def parse(self, bundle: Bundle) -> Iterator[ParsedEntry]:
        for f in bundle.files(MARKDOWN_SUFFIXES):
            raw = bundle.read_text(f.rel_path)
            _, body = split_frontmatter(raw)
            content = _clean(body)
            if not _is_meaningful(content):
                continue
            yield ParsedEntry(
                content=content,
                date=best(from_frontmatter(raw), from_filename(f.stem),
                          from_path(f.rel_path)),
                title=None,
                source_path=f.rel_path,
                likely_generated=generated_reason(raw, f.rel_path),
            )


#: The earlier IRIS recorded these beside the prose, on its own scales. They
#: were read as text or dropped entirely, so every imported entry arrived with
#: no energy, no clarity, and a mood nobody had given it.
_IRIS_OG_METRICS = {
    "mood": ("mood", "1-10"),
    "energy": ("energy", "1-10"),
    "sleep_hours": ("sleep_hours", "hours"),
    "sleep_quality": ("sleep_quality", "1-10"),
    "exercise": ("exercise", "as recorded"),
    "nutrition": ("nutrition", "as recorded"),
    "anxiety": ("anxiety", "1-10"),
    "stress": ("stress", "1-10"),
}


def _iris_og_metrics(entry: dict) -> dict:
    """The typed values an entry recorded, each with the scale it was on.

    Kept separately from the prose: a number the owner entered is a
    measurement, and running it into a sentence loses both the value and the
    scale it was measured against.
    """
    wellbeing = entry.get("wellbeing") or {}
    out = {}
    for key, (name, scale) in _IRIS_OG_METRICS.items():
        value = wellbeing.get(key)
        if value in (None, "", []):
            continue
        out[name] = {"value": value, "scale": scale, "source": "iris_og.wellbeing"}
    return out


_IRIS_OG_SECTIONS = (
    ("what_went_well", "What went well"),
    ("what_to_improve", "What to improve"),
    ("key_insight", "Key insight"),
    ("tomorrow_priorities", "Tomorrow's priorities"),
)


def _iris_og_text(entry: dict) -> str:
    """The prose of an earlier-IRIS entry, in the order the owner wrote it.

    `reflections` is a string in most entries and a dict of named prompts in the
    later ones (the "evening" preset). Both are the owner's own words; the dict
    keys become headings so the structure survives rather than being run
    together. Ideas, goals and execution are kept as labelled lists: they are
    what the owner wrote that day — a goal here is text in a journal, not a
    claim that anything was done.
    """
    parts: list[str] = []
    refl = entry.get("reflections")
    if isinstance(refl, dict):
        for key, label in _IRIS_OG_SECTIONS:
            if str(refl.get(key) or "").strip():
                parts.append(f"{label}: {str(refl[key]).strip()}")
        for key, value in refl.items():
            if key not in dict(_IRIS_OG_SECTIONS) and str(value or "").strip():
                parts.append(f"{key.replace('_', ' ').capitalize()}: {str(value).strip()}")
    elif str(refl or "").strip():
        parts.append(str(refl).strip())

    notes = (entry.get("wellbeing") or {}).get("notes")
    if str(notes or "").strip():
        parts.append(f"Notes: {str(notes).strip()}")

    for key, label in (("ideas", "Ideas"), ("goals", "Goals"), ("execution", "Done")):
        items = [str(i).strip() for i in (entry.get(key) or []) if str(i).strip()]
        if items:
            parts.append(label + ":\n" + "\n".join(f"- {i}" for i in items))
    return _clean("\n\n".join(parts))


class IrisOGJournalAdapter:
    name = "iris_og_journal"
    label = "Earlier IRIS journal"
    description = ("Journal entries saved by an earlier version of IRIS: a JSON list "
                   "with a timestamp, wellbeing and reflections on every entry.")

    def _payloads(self, bundle: Bundle) -> Iterator[tuple[str, list]]:
        for f in bundle.files({".json"}):
            try:
                data = json.loads(bundle.read_text(f.rel_path))
            except (ValueError, OSError):
                continue
            if not (isinstance(data, list) and data and isinstance(data[0], dict)):
                continue
            sample = data[:20]
            # `reflections` is what distinguishes this from the companion's own
            # re-packaging of the same entries (which carries `text` instead) —
            # importing both would count every entry twice.
            if sum(1 for e in sample if isinstance(e, dict)
                   and "date" in e and "reflections" in e) >= 0.8 * len(sample):
                yield f.rel_path, data

    def sniff(self, bundle: Bundle) -> float:
        return 0.95 if next(self._payloads(bundle), None) else 0.0

    def parse(self, bundle: Bundle) -> Iterator[ParsedEntry]:
        for rel, data in self._payloads(bundle):
            for i, entry in enumerate(data):
                if not isinstance(entry, dict):
                    continue
                content = _iris_og_text(entry)
                if not _is_meaningful(content):
                    continue
                # A naive local timestamp, as the old app wrote it. Its date is
                # the day as the owner lived it, which is the day that matters.
                yield ParsedEntry(
                    content=content,
                    date=parse_timestamp(entry.get("date") or entry.get("created_at") or ""),
                    metrics=_iris_og_metrics(entry) or None,
                    title=entry.get("preset_used") or entry.get("time_of_day"),
                    source_path=f"{rel}#{entry.get('id', i)}",
                )


# Checked against the real export before deciding to drop these: 8 <aside>
# blocks across 89 entries, **one** distinct text between them (152 chars, tip
# marker, "Notion Tip"), and all 8 sit beside prose the owner wrote. It is one
# piece of template furniture repeated 8 times, so keeping it would copy an
# identical string into 8 entries and hand the engines a phrase that recurs
# without anyone having written it twice.
_ASIDE = re.compile(r"<aside>.*?</aside>", re.S | re.I)


class ElaraJournalAdapter:
    name = "elara_journal"
    label = "Personal Assistant (Elara) journal export"
    description = ("Journal entries combined by the Elara project: one JSON file with "
                   "metadata and a list of entries converted from Notion.")

    def _payloads(self, bundle: Bundle) -> Iterator[tuple[str, dict]]:
        for f in bundle.files({".json"}):
            try:
                data = json.loads(bundle.read_text(f.rel_path))
            except (ValueError, OSError):
                continue
            if not (isinstance(data, dict) and isinstance(data.get("metadata"), dict)
                    and isinstance(data.get("entries"), list) and data["entries"]):
                continue
            sample = data["entries"][:20]
            if sum(1 for e in sample if isinstance(e, dict)
                   and "content" in e and "filename" in e) >= 0.8 * len(sample):
                yield f.rel_path, data

    def sniff(self, bundle: Bundle) -> float:
        return 0.96 if next(self._payloads(bundle), None) else 0.0

    def parse(self, bundle: Bundle) -> Iterator[ParsedEntry]:
        for rel, data in self._payloads(bundle):
            for i, entry in enumerate(data["entries"]):
                if not isinstance(entry, dict):
                    continue
                # Notion's <aside> callouts are template boilerplate, not writing.
                content = _clean(_ASIDE.sub("", str(entry.get("content") or "")))
                if not _is_meaningful(content):
                    continue

                stem = str(entry.get("filename") or "").rsplit(".", 1)[0]
                named = best(from_filename(_NOTION_ID.sub("", stem)),
                             parse_date_text(str(entry.get("title") or "")))
                declared = str(entry.get("date") or "")[:10]
                modified = str(entry.get("modified") or "")[:10]
                warnings: list[str] = []

                if named.known:
                    date = named
                elif declared and declared != modified:
                    guess = parse_date_text(declared)
                    date = (DateGuess(guess.value, "json_field", "probable", raw=declared,
                                      note="taken from the export's date field")
                            if guess.known else UNKNOWN)
                else:
                    # The trap this adapter exists to avoid. The export writes
                    # the day it was *made* into `date` for most entries — on the
                    # real archive, 80 of 89 read 2025-10-18 — so trusting it
                    # would pile a year of writing onto one day and every window
                    # would see a spike that never happened.
                    date = UNKNOWN
                    if declared:
                        warnings.append(
                            f"The export dates this {declared}, which is the day the "
                            "export was made, not the day it was written."
                        )

                # Its `tags` are Notion page properties the export failed to
                # parse ("Daily\n\nIt is so hard to…"), so they are not used.
                yield ParsedEntry(
                    content=content,
                    date=date,
                    title=str(entry.get("title") or "") or None,
                    source_path=f"{rel}#{entry.get('id', i)}",
                    warnings=warnings,
                    likely_generated=generated_reason(content),
                )


def _is_number(text: str) -> bool:
    """A transcriber's confidence score, as opposed to a remark about the clip."""
    try:
        float(text.strip())
    except ValueError:
        return False
    return True


class TelegramVoiceAdapter:
    """A transcript document: one file, many spoken entries, no dates.

    The owner's voice journal was transcribed from Telegram voice messages in a
    single Whisper run, so every entry carries the same "exported 2026-07-26
    17:02 UTC" line — the moment the transcriber wrote the files out, not when
    anything was said. Reading that as the date would put nine hours of speech
    on one afternoon, which is the Elara trap exactly (ADR-0013). The order is
    real and is kept; the dates are absent and stay absent until the owner
    supplies them or a Telegram export does.

    Without this, the registry falls through to `plain_files` and the whole
    document becomes one 61,000-word entry.
    """

    name = "telegram_voice"
    label = "Voice transcripts (one file, many recordings)"
    description = "A transcript document whose entries are numbered recordings, each with its length."

    #: "## 12. Some title" — the numbering is the chronological order.
    _ENTRY = re.compile(r"^##\s+(\d+)\.\s*(.*\S)\s*$", re.M)
    #: "*14:16 · en (0.99) · exported 2026-07-26 17:02 UTC*"
    _META = re.compile(r"^\*(\d{1,2}):(\d{2})\s·\s([^\s(]+)\s*\(([^)]*)\)(.*?)\*\s*$", re.M)
    _ANCHOR = re.compile(r"^\[[^\]]*\]\(#[^)]*\)\s*$", re.M)

    def _files(self, bundle: Bundle) -> list[BundleFile]:
        # Structure is the discriminator — numbered headings each followed by a
        # duration line — not size. The floor only keeps a stub out.
        return [f for f in bundle.files(MARKDOWN_SUFFIXES) if f.size > 400]

    def _entries(self, text: str) -> list[tuple[int, str, str, re.Match | None]]:
        out = []
        marks = list(self._ENTRY.finditer(text))
        for i, m in enumerate(marks):
            body = text[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(text)]
            meta = self._META.search(body)
            if not meta:
                continue  # a contents block, not a recording
            out.append((int(m[1]), m[2], body, meta))
        return out

    def sniff(self, bundle: Bundle) -> float:
        files = self._files(bundle)
        if len(files) != 1:
            return 0.0
        found = self._entries(bundle.read_text(files[0].rel_path))
        # Numbered headings *and* a duration line under each: a plain numbered
        # list of notes does not have the second.
        return 0.92 if len(found) >= 3 else 0.0

    def parse(self, bundle: Bundle) -> Iterator[ParsedEntry]:
        for f in self._files(bundle):
            for number, title, body, meta in self._entries(bundle.read_text(f.rel_path)):
                minutes, seconds, language, bracket, tail = meta.groups()
                spoken = self._META.sub("", body)
                spoken = self._ANCHOR.sub("", spoken)
                content = _clean(spoken)
                if not _is_meaningful(content):
                    continue
                warnings = [
                    f"Recording {number}, {int(minutes)}:{seconds} long. The transcript file "
                    "carries no date — its timestamp is when the transcription ran."
                ]
                # The bracket holds either a confidence score or the
                # transcriber's prose; the tail holds remarks such as
                # "near-empty clip" before the "exported ..." stamp. A score is
                # not a remark, and the stamp is not one either.
                remarks = []
                if not _is_number(bracket):
                    remarks.append(bracket.strip())
                for part in tail.split("·"):
                    part = part.strip()
                    if part and not part.startswith("exported"):
                        remarks.append(part)
                if remarks:
                    warnings.append("The transcriber noted: " + "; ".join(remarks) + ".")
                yield ParsedEntry(
                    content=content,
                    date=UNKNOWN,
                    title=title,
                    # The number keeps the chronological order the file states.
                    source_path=f"{f.rel_path}#{number:03d}",
                    tags=[language] if language and language.isalpha() else [],
                    warnings=warnings,
                )


REGISTRY: list[SourceAdapter] = [
    DayOneAdapter(), IrisOGJournalAdapter(), ElaraJournalAdapter(), NotionAdapter(),
    TelegramVoiceAdapter(), DatedFilesAdapter(), SingleFileAdapter(), CsvAdapter(),
    PlainFilesAdapter(),
]


def get(name: str) -> SourceAdapter:
    for adapter in REGISTRY:
        if adapter.name == name:
            return adapter
    raise KeyError(f"unknown import format: {name!r}")


def detect(bundle: Bundle) -> list[dict]:
    """Every adapter that recognises this bundle, best first."""
    scored = []
    for adapter in REGISTRY:
        try:
            score = float(adapter.sniff(bundle))
        except Exception as e:
            logger.warning(f"{adapter.name} failed to sniff the bundle: {e}")
            continue
        if score > 0:
            scored.append({"adapter": adapter.name, "label": adapter.label,
                           "description": adapter.description, "score": round(score, 3)})
    return sorted(scored, key=lambda d: d["score"], reverse=True)


def parse_with(bundle: Bundle, adapter_name: str) -> list[ParsedEntry]:
    return list(get(adapter_name).parse(bundle))
