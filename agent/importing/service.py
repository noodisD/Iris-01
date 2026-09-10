"""
Taking an upload from a file to entries IRIS can reason about.

The shape is upload → parse → stage → review → commit, and the review step is
not optional. The source format is not known in advance, dates come from
filenames and property blocks written by other tools, and an export contains
things that are not journal entries at all. Every one of those is cheap to
correct before a reflection exists and expensive afterwards: once an entry has
been embedded and matched to a theme, undoing it is real work.

Committing goes through `ReflectionService.create_reflection`, the same seam the
app and the CLI write through. That is deliberate — the entry is enqueued,
embedded and offered to the analytical engines exactly like anything else, and
importing does not become a second way for data to enter the system.
"""

from __future__ import annotations

import logging
import shutil
from datetime import date
from pathlib import Path

import psycopg2

from ..config import settings
from ..trackers.reflections import ReflectionService
from . import store
from .adapters import ParsedEntry, detect, get
from .archive import UnsafeArchive, extract_safely
from .bundle import Bundle

logger = logging.getLogger(__name__)


def data_root() -> Path:
    return Path(settings.DATA_DIR).expanduser().resolve()


def _batch_workspace(batch_id: int) -> Path:
    return data_root() / "imports" / str(batch_id)


class ImportError_(Exception):
    """Something about the upload itself is wrong, and the owner should be told."""


class ImportService:
    def __init__(self, user_id: int):
        self.user_id = user_id

    # --- staging ----------------------------------------------------------

    def create_batch(self, upload: Path, original_filename: str,
                     kind: str = "text", adapter: str | None = None) -> dict:
        """Register an upload, read it, and stage what it contains."""
        batch_id = store.create_batch(self.user_id, kind, original_filename, None)
        workspace = _batch_workspace(batch_id)
        workspace.mkdir(parents=True, exist_ok=True)

        stored = workspace / "upload"
        stored.mkdir(exist_ok=True)
        destination = stored / Path(original_filename).name
        shutil.move(str(upload), destination)
        store.update_batch(batch_id, status="parsing")

        try:
            bundle = self._open(destination, workspace)
            self._stage(batch_id, bundle, adapter)
        except UnsafeArchive as e:
            store.update_batch(batch_id, status="failed", error=str(e))
            raise ImportError_(str(e)) from e
        except Exception as e:
            logger.exception(f"Import batch {batch_id} failed while parsing")
            store.update_batch(batch_id, status="failed", error=str(e))
            raise
        return self.get_batch(batch_id)

    def _open(self, uploaded: Path, workspace: Path) -> Bundle:
        """A Bundle over the upload, whether it arrived as an archive or a file."""
        extracted = workspace / "extracted"
        if uploaded.suffix.lower() == ".zip":
            extract_safely(uploaded, extracted)
        else:
            # A single file is a bundle of one. Same code path from here on, so
            # nothing downstream needs to know how the upload arrived.
            extracted.mkdir(parents=True, exist_ok=True)
            shutil.copy2(uploaded, extracted / uploaded.name)
        return Bundle(extracted)

    def _stage(self, batch_id: int, bundle: Bundle, adapter: str | None) -> None:
        found = detect(bundle)
        chosen = adapter or (found[0]["adapter"] if found else None)
        if not chosen:
            store.update_batch(batch_id, status="failed", detected=[],
                               error="Nothing in this upload looked like journal entries.")
            raise ImportError_("Nothing in this upload looked like journal entries.")

        entries = list(get(chosen).parse(bundle))
        store.replace_items(batch_id, self.user_id,
                            [self._to_item(e) for e in entries])
        store.mark_duplicates(batch_id, self.user_id)
        store.update_batch(batch_id, status="needs_review", adapter=chosen,
                           detected=found, entry_count=len(entries), error=None)

    @staticmethod
    def _to_item(entry: ParsedEntry) -> dict:
        return {
            "source_name": entry.source_path,
            "title": entry.title,
            "content": entry.content,
            "content_hash": store.content_hash(entry.content),
            "entry_date": entry.date.value,
            "date_source": entry.date.source,
            "date_confidence": entry.date.confidence,
            "tags": entry.tags,
            "warnings": entry.warnings + ([entry.date.note] if entry.date.note else []),
        }

    def reparse(self, batch_id: int, adapter: str) -> dict:
        """Read the same upload again as a different format.

        Detection is a guess; this is how the owner overrules it. Staged rows are
        replaced wholesale so a change of format cannot leave a mixture of two
        readings behind.
        """
        batch = self._require(batch_id)
        if batch["status"] not in ("needs_review", "failed"):
            raise ImportError_("This import has already been committed.")
        workspace = _batch_workspace(batch_id)
        bundle = Bundle(workspace / "extracted")
        store.update_batch(batch_id, status="parsing")
        self._stage(batch_id, bundle, adapter)
        return self.get_batch(batch_id)

    # --- reading ----------------------------------------------------------

    def _require(self, batch_id: int) -> dict:
        batch = store.get_batch(batch_id, self.user_id)
        if not batch:
            raise ImportError_("No such import.")
        return batch

    def get_batch(self, batch_id: int) -> dict:
        batch = self._require(batch_id)
        batch["counts"] = store.counts(batch_id)
        return batch

    def list_batches(self, limit: int = 25) -> list[dict]:
        return store.list_batches(self.user_id, limit)

    def list_items(self, batch_id: int, status: str | None = None,
                   limit: int = 500, offset: int = 0) -> list[dict]:
        self._require(batch_id)
        return store.list_items(batch_id, self.user_id, status, limit, offset)

    # --- correcting -------------------------------------------------------

    def update_item(self, item_id: int, entry_date: date | None = None,
                    status: str | None = None, content: str | None = None) -> dict:
        item = store.get_item(item_id, self.user_id)
        if not item:
            raise ImportError_("No such entry in this import.")

        fields: dict = {}
        if entry_date is not None:
            # A date the owner supplied is the most certain kind there is.
            fields.update(entry_date=entry_date, date_source="user",
                          date_confidence="certain")
        if status is not None:
            if status not in ("staged", "excluded"):
                raise ImportError_("An entry can only be included or excluded.")
            fields["status"] = status
        if content is not None:
            fields.update(content=content, content_hash=store.content_hash(content))

        updated = store.update_item(item_id, self.user_id, **fields)
        if entry_date is not None or content is not None:
            store.mark_duplicates(item["batch_id"], self.user_id)
        return updated or {}

    def bulk(self, item_ids: list[int], op: str, entry_date: date | None = None) -> int:
        if op == "exclude":
            return store.bulk_update(item_ids, self.user_id, status="excluded")
        if op == "include":
            return store.bulk_update(item_ids, self.user_id, status="staged")
        if op == "set_date":
            if entry_date is None:
                raise ImportError_("A date is required to set one.")
            return store.bulk_update(item_ids, self.user_id, entry_date=entry_date,
                                     date_source="user", date_confidence="certain")
        raise ImportError_(f"Unknown operation {op!r}.")

    # --- committing -------------------------------------------------------

    def commit(self, batch_id: int) -> dict:
        """Turn the staged entries into reflections.

        Refuses while any included entry has no date. That is the same rule the
        parser enforces, restated where it can actually be broken: a commit is
        the last moment an unknown date can be caught before it becomes
        occurred_at and silently moves an entry into the wrong window.
        """
        batch = self._require(batch_id)
        if batch["status"] == "committed":
            raise ImportError_("This import has already been committed.")

        counts = store.counts(batch_id)
        if counts.get("needs_date"):
            raise ImportError_(
                f"{counts['needs_date']} entries still have no date. Set them, or "
                "exclude them, before importing."
            )

        store.update_batch(batch_id, status="committing")
        reflections = ReflectionService(self.user_id)
        committed = failed = duplicates = 0

        for item in store.list_items(batch_id, self.user_id, status="staged", limit=100_000):
            try:
                reflection_id = reflections.create_reflection(
                    content=item["content"],
                    reflection_date=item["entry_date"],
                    tags=item["tags"] or [],
                    source="voice" if item["audio_path"] else "import",
                    content_hash=item["content_hash"],
                    audio_path=item["audio_path"],
                )
            except psycopg2.errors.UniqueViolation:
                # The index caught what the pre-flight sweep missed — a race, or
                # an entry the owner re-included by hand. Not an error.
                store.update_item(item["id"], self.user_id, status="duplicate")
                duplicates += 1
                continue
            except Exception as e:
                logger.exception(f"Import item {item['id']} failed")
                store.update_item(item["id"], self.user_id, status="failed", error=str(e))
                failed += 1
                continue
            store.update_item(item["id"], self.user_id, status="imported",
                              reflection_id=reflection_id, error=None)
            committed += 1

        store.update_batch(batch_id, status="committed", committed_count=committed)
        if committed:
            _kick_the_queue()

        return {"committed": committed, "duplicates": duplicates, "failed": failed,
                "excluded": store.counts(batch_id).get("excluded", 0)}

    # --- undoing ----------------------------------------------------------

    def delete_batch(self, batch_id: int, with_reflections: bool = False) -> dict:
        """Discard a staged batch, or undo a committed one.

        Undo exists because the dates are the point. If an export was read with
        the wrong format and four hundred entries landed on the wrong days, the
        answer has to be better than living with it.
        """
        self._require(batch_id)
        removed = 0
        if with_reflections:
            from ..database import db, themes

            reflection_ids = store.reflection_ids_for_batch(batch_id, self.user_id)
            affected: set[int] = set()
            for reflection_id in reflection_ids:
                with db.connection() as conn, conn.cursor() as cur:
                    cur.execute(
                        """SELECT theme_id FROM theme_occurrences
                           WHERE source_type = 'reflection' AND source_id = %s;""",
                        (reflection_id,),
                    )
                    affected.update(r[0] for r in cur.fetchall())
                db.delete_reflection(reflection_id)
                removed += 1

            # Theme aggregates are derived from the occurrences that remain, so
            # refreshing them is enough; a theme with nothing left is not a
            # theme, and CONTEXT.md requires every one to have an occurrence.
            for theme_id in affected:
                with db.connection() as conn, conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM theme_occurrences WHERE theme_id = %s;",
                        (theme_id,),
                    )
                    if cur.fetchone()[0] == 0:
                        db.delete_theme(theme_id)
                        continue
                themes.update_stats(theme_id, None)

        store.delete_batch(batch_id, self.user_id)
        shutil.rmtree(_batch_workspace(batch_id), ignore_errors=True)
        return {"deleted": True, "reflections_removed": removed}


def _kick_the_queue() -> None:
    """Ask the running worker for a pass now instead of at its next poll.

    The worker wakes every 30 seconds and takes 20 items, so a few hundred
    entries would otherwise trickle in for minutes after the page says the
    import finished. Where no worker is running — tests, the CLI — this does
    nothing and the caller drains when it wants the work done.
    """
    from ..work_queue import worker

    worker.wake()
