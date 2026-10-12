"""Long entries recalled by passage, and dictated ones read from their reading copy.

Every entry below is invented. Embeddings are the offline fakes from conftest.
"""

from __future__ import annotations

import json
from datetime import date

from agent import discovery_worker, pipeline
from agent.core import PersonalAICompanion
from agent.database import db
from agent.entry_passages import MAX_WORDS, MIN_WORDS, TAIL_WORDS, cut
from agent.readable import current_copy, ensure_copy, same_words
from agent.trackers.reflections import ReflectionService

SENTENCES = [
    "The pottery class ran late again because the kiln was still cooling.",
    "I walked home along the canal and counted the herons on the far bank.",
    "My sister rang about the garden and we argued about where the beans should go.",
    "In the evening I fixed the bicycle chain with a borrowed tool.",
]


def _long_entry(paragraphs: int = 6, per: int = 5) -> str:
    return "\n\n".join(" ".join(SENTENCES[(p + k) % 4] for k in range(per)) for p in range(paragraphs))


def _words(text: str) -> list[str]:
    return text.split()


# --- the cut -------------------------------------------------------------------------

def test_a_short_entry_is_recalled_whole():
    assert cut(" ".join(["word"] * MIN_WORDS)) == []


def test_a_long_entry_is_cut_into_whole_sentences_with_every_word_kept_in_order():
    text = _long_entry()
    passages = cut(text)
    assert len(passages) > 1
    assert _words(" ".join(passages)) == _words(text)
    assert all(len(p.split()) <= MAX_WORDS + TAIL_WORDS for p in passages)
    assert all(p.rstrip().endswith(".") for p in passages), "a passage ends at a sentence end"


def test_an_entry_with_no_sentence_breaks_is_cut_at_words():
    text = " ".join(f"word{i}" for i in range(700))
    passages = cut(text)
    assert _words(" ".join(passages)) == _words(text)
    assert max(len(p.split()) for p in passages) <= MAX_WORDS + TAIL_WORDS


# --- stored, recalled, and gone with the entry ---------------------------------------

def _passages(reflection_id: int) -> list[tuple[int, str]]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, text FROM entry_passages WHERE reflection_id = %s ORDER BY position;",
                    (reflection_id,))
        return cur.fetchall()


def _vectors(ids: list[int]) -> int:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM embeddings WHERE source_type = 'entry_passage' AND source_id = ANY(%s);",
                    (ids,))
        return cur.fetchone()[0]


def test_a_long_entry_is_found_by_its_passages_and_they_go_with_it(test_user):
    service = ReflectionService(test_user["id"])
    long_id = service.create_reflection(content=_long_entry(), reflection_date=date(2025, 5, 4))
    short_id = service.create_reflection(content="A short note about the herons.", reflection_date=date(2025, 5, 5))
    pipeline.run_processing_pipeline("reflection", long_id)
    pipeline.run_processing_pipeline("reflection", short_id)

    passages = _passages(long_id)
    assert len(passages) > 1 and not _passages(short_id)
    assert _vectors([p[0] for p in passages]) == len(passages)
    item = db.get_memory_item("entry_passage", passages[0][0])
    assert item == {"kind": "journal", "date": date(2025, 5, 4), "text": passages[0][1]}

    found = db.search_similar_embeddings(test_user["id"], [0.1] * 1536, n_results=100)
    kinds = {(r["source_type"], r["source_id"]) for r in found}
    assert ("reflection", long_id) not in kinds, "a long entry's averaged vector is not searched"
    assert ("reflection", short_id) in kinds
    assert {("entry_passage", p[0]) for p in passages} <= kinds

    service.update_reflection(long_id, content="Now only a short line.")
    assert not _passages(long_id) and _vectors([p[0] for p in passages]) == 0

    pipeline.run_processing_pipeline("reflection", long_id)
    service.update_reflection(long_id, content=_long_entry(5))
    pipeline.run_processing_pipeline("reflection", long_id)
    again = [p[0] for p in _passages(long_id)]
    assert again
    db.delete_reflection(long_id)
    assert _vectors(again) == 0


def test_chat_shows_the_passage_that_matched_whole_and_says_it_is_part_of_more(test_user, mocker):
    service = ReflectionService(test_user["id"])
    long_id = service.create_reflection(content=_long_entry(), reflection_date=date(2024, 3, 2))
    for day in range(1, 6):
        service.create_reflection(content=f"Recent note {day}", reflection_date=date(2026, 1, day))
    pipeline.run_processing_pipeline("reflection", long_id)
    passage_id, text = _passages(long_id)[1]

    mocker.patch("agent.core.generate_embedding", return_value=[0.1] * 1536)
    mocker.patch.object(db, "search_similar_embeddings", return_value=[
        {"source_type": "entry_passage", "source_id": passage_id, "distance": 0.05}])
    memories = PersonalAICompanion(user_id=test_user["id"])._get_relevant_context("herons")
    assert f"[journal, 2024-03-02, part of a longer entry] {' '.join(text.split())}" in memories


# --- reading copies ----------------------------------------------------------------

RAW = ("so today i went to the pottery class again and the wheel kept wobbling and i couldnt "
       "centre the clay at all then near the end it just worked and i got a bowl out of it "
       "and then i walked home along the canal")


class Ends:
    def __init__(self, *ends):
        self.ends = list(ends)

    def chat(self, messages, system_prompt, **kwargs):
        return json.dumps({"sentence_ends": self.ends})


def test_a_dictated_entry_gets_a_copy_kept_only_while_its_words_are_the_entrys(test_user):
    service = ReflectionService(test_user["id"])
    reflection_id = service.create_reflection(content=RAW, reflection_date=date(2025, 1, 2))
    copy = ensure_copy(reflection_id, RAW, None, Ends("and the wheel kept wobbling", "a bowl out of it"))
    assert copy and copy != RAW and same_words(RAW, copy)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT reading_copy FROM reflections WHERE id = %s;", (reflection_id,))
        assert cur.fetchone()[0] == copy
    assert current_copy(RAW + " and slept", copy) is None, "a copy of other words is never used"

    service.update_reflection(reflection_id, content=RAW + " and slept early")
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT reading_copy FROM reflections WHERE id = %s;", (reflection_id,))
        assert cur.fetchone()[0] is None, "an edit clears the copy"


def test_the_reader_reads_the_copy_and_entries_can_be_read_again(test_user, monkeypatch):
    service = ReflectionService(test_user["id"])
    reflection_id = service.create_reflection(content=RAW, reflection_date=date(2025, 1, 2))
    copy = ensure_copy(reflection_id, RAW, None, Ends("and the wheel kept wobbling"))
    seen = []

    def read(self, entries, readable=None):
        seen.append(readable)
        return []
    monkeypatch.setattr(discovery_worker.EpisodeReader, "read", read)
    discovery_worker.process_reflection(reflection_id)
    assert seen == [{str(reflection_id): copy}]

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT discovery_revision FROM reflections WHERE id = %s;", (reflection_id,))
        before = cur.fetchone()[0]
    assert db.reread_entries(test_user["id"], [reflection_id]) == 1
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT discovery_revision FROM reflections WHERE id = %s;", (reflection_id,))
        assert cur.fetchone()[0] == before + 1
        cur.execute("SELECT count(*) FROM processing_queue WHERE source_type = 'discovery' AND source_id = %s;",
                    (reflection_id,))
        assert cur.fetchone()[0] == 1
