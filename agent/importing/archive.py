"""
Unpacking an uploaded archive without trusting it.

Exports arrive as zips — Notion, Day One and Obsidian all produce them. A zip is
a list of names and sizes supplied by whoever made the file, and every field in
it is a claim rather than a fact, so nothing here is taken at face value.

`ZipFile.extractall` is not used. It sanitises `..` in member names, which is
the attack everyone knows about, and then happily writes a symlink — after which
the next member written "through" that link lands wherever the link points.
That is the hole worth closing deliberately.
"""

from __future__ import annotations

import logging
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_MEMBERS = 20_000
MAX_TOTAL_BYTES = 2 * 1024**3        # 2 GiB uncompressed
MAX_MEMBER_BYTES = 256 * 1024**2     # 256 MiB for any one file
MAX_RATIO = 200                      # uncompressed:compressed, per member

_S_IFLNK = 0o120000
_S_IFMT = 0o170000
_UNSAFE_NAME = re.compile(r"\x00|^[/\\]|^[A-Za-z]:|(^|[/\\])\.\.([/\\]|$)")


class UnsafeArchive(Exception):
    """The archive asked for something it should not have."""


@dataclass
class ExtractResult:
    root: Path
    file_count: int
    total_bytes: int


def _reject(name: str, why: str) -> None:
    raise UnsafeArchive(f"refused {name!r}: {why}")


def _check_name(name: str) -> None:
    if _UNSAFE_NAME.search(name):
        _reject(name, "absolute path, drive letter, parent traversal or null byte")
    if len(name.encode("utf-8", "surrogatepass")) > 1024:
        _reject(name, "name is implausibly long")


def extract_safely(archive: Path, dest: Path) -> ExtractResult:
    """Extract `archive` into `dest`, or raise UnsafeArchive."""
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()

        if len(infos) > MAX_MEMBERS:
            _reject(archive.name, f"{len(infos)} members, limit {MAX_MEMBERS}")

        declared = sum(i.file_size for i in infos)
        if declared > MAX_TOTAL_BYTES:
            _reject(archive.name, f"declares {declared} bytes, limit {MAX_TOTAL_BYTES}")

        for info in infos:
            _check_name(info.filename)
            mode = (info.external_attr >> 16) & _S_IFMT
            if mode == _S_IFLNK:
                # The one people miss. A symlink is not a file we need from a
                # journal export, and admitting it lets a later member escape.
                _reject(info.filename, "archive contains a symlink")
            if info.file_size > MAX_MEMBER_BYTES:
                _reject(info.filename, f"member is {info.file_size} bytes")
            if info.compress_size and info.file_size / info.compress_size > MAX_RATIO:
                _reject(info.filename, "compression ratio looks like a zip bomb")

        written = 0
        count = 0
        for info in infos:
            target = (dest / info.filename).resolve()
            # Belt and braces: the name checks above should make this
            # unreachable, but the cost of being wrong is writing outside dest.
            if not target.is_relative_to(dest):
                _reject(info.filename, "resolves outside the destination")

            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as out:
                # Copy through a budget rather than trusting file_size: the
                # header is the archive's claim about itself, and the actual
                # stream is free to disagree with it.
                remaining = MAX_TOTAL_BYTES - written
                for chunk in iter(lambda: src.read(1 << 20), b""):
                    remaining -= len(chunk)
                    if remaining < 0:
                        out.close()
                        shutil.rmtree(dest, ignore_errors=True)
                        _reject(info.filename, "archive expands past the size budget")
                    out.write(chunk)
                    written += len(chunk)
            count += 1

    logger.info(f"Extracted {count} files ({written} bytes) from {archive.name}")
    return ExtractResult(root=dest, file_count=count, total_bytes=written)
