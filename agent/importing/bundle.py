"""
A read-only view over the files an export contains.

Adapters are handed one of these and nothing else. They never see an absolute
path, never see the zip, and never touch the filesystem directly — which keeps
them trivially testable against a fixture directory and keeps path handling in
one place instead of repeated in every format.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Files an export might contain that carry no journal content. Skipped so a
#: sniffer is not confused by a `.DS_Store` and an adapter is not handed one.
_IGNORED_NAMES = {".DS_Store", "Thumbs.db", ".gitkeep"}
_IGNORED_DIRS = {"__MACOSX", ".git", "node_modules"}

TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".text", ".json", ".csv"}


@dataclass(frozen=True)
class BundleFile:
    rel_path: str
    size: int

    @property
    def name(self) -> str:
        return self.rel_path.rsplit("/", 1)[-1]

    @property
    def suffix(self) -> str:
        name = self.name
        return name[name.rfind("."):].lower() if "." in name else ""

    @property
    def stem(self) -> str:
        name = self.name
        return name[: name.rfind(".")] if "." in name else name


class Bundle:
    """The extracted contents of one upload."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def files(self, suffixes: set[str] | None = None) -> list[BundleFile]:
        found = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            if path.name in _IGNORED_NAMES or path.name.startswith("._"):
                continue
            rel = path.relative_to(self.root).as_posix()
            if any(part in _IGNORED_DIRS for part in rel.split("/")):
                continue
            if suffixes and path.suffix.lower() not in suffixes:
                continue
            found.append(BundleFile(rel_path=rel, size=path.stat().st_size))
        return found

    def text_files(self) -> list[BundleFile]:
        return self.files(TEXT_SUFFIXES)

    def _resolve(self, rel_path: str) -> Path:
        target = (self.root / rel_path).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError(f"{rel_path!r} is outside the bundle")
        return target

    def read_bytes(self, rel_path: str) -> bytes:
        return self._resolve(rel_path).read_bytes()

    def read_text(self, rel_path: str) -> str:
        # Exports come from every operating system there is; a single mis-encoded
        # character should not cost the entry.
        raw = self.read_bytes(rel_path)
        for encoding in ("utf-8", "utf-8-sig", "cp1252"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")
