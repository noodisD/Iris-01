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
from typing import Iterator, Protocol

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
    title: str | None = None
    source_path: str = ""
    tags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


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
            )


REGISTRY: list[SourceAdapter] = [
    DayOneAdapter(), NotionAdapter(), DatedFilesAdapter(),
    SingleFileAdapter(), CsvAdapter(), PlainFilesAdapter(),
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
