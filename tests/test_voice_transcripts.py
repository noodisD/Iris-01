"""A transcript document: many recordings, one file, no dates.

The owner's voice journal reached IRIS as a single Whisper transcript of 43
Telegram voice messages. Every entry in it reads "exported 2026-07-26 17:02
UTC" — when the transcriber wrote the files out, not when anything was said —
and nine hours of speech landing on one afternoon is the Elara trap again
(ADR-0013). Without an adapter the registry reads the whole document as one
61,000-word entry.

Every word of transcript below is invented.
"""

from __future__ import annotations

import pytest

from agent.importing import Bundle, detect, get

DOC = """# Telegram Voice Message Transcripts

- **Files:** 3 · **Total audio:** 0:21:30
- **Transcribed:** 2026-07-26 19:59 · **Model:** OpenAI Whisper large-v3 (local, GPU)

---

## Contents

1. [Morning walk](#1-morning-walk) · 14:16
2. [After the call](#2-after-the-call) · 2:34
3. [Late one](#3-late-one) · 0:05

---

## 1. Morning walk

*14:16 · en (0.99) · exported 2026-07-26 17:02 UTC*

Walked the long way round before work and thought about the deadline the whole time.

[↑ Contents](#contents)

## 2. After the call

*2:34 · en (0.98) · exported 2026-07-26 17:02 UTC*

That went better than I expected, though I still talked too fast at the start.

[↑ Contents](#contents)

## 3. Late one

*0:05 · nn (0.68) · near-empty clip · exported 2026-07-26 17:02 UTC*

Testing this thing again.

[↑ Contents](#contents)
"""


@pytest.fixture
def bundle(tmp_path):
    (tmp_path / "Telegram Voice Transcripts.md").write_text(DOC, encoding="utf-8")
    return Bundle(tmp_path)


def test_the_document_is_recognised(bundle):
    assert detect(bundle)[0]["adapter"] == "telegram_voice"


def test_each_recording_becomes_its_own_entry(bundle):
    entries = list(get("telegram_voice").parse(bundle))
    assert len(entries) == 3, "the whole document used to arrive as one entry"
    assert entries[0].content.startswith("Walked the long way round")
    assert "exported" not in entries[0].content and "↑ Contents" not in entries[0].content


def test_the_contents_block_is_not_an_entry(bundle):
    titles = [e.title for e in get("telegram_voice").parse(bundle)]
    assert "Contents" not in titles


def test_the_export_timestamp_is_not_taken_as_a_date(bundle):
    """Nine hours of speech on one afternoon is what trusting it would mean."""
    entries = list(get("telegram_voice").parse(bundle))
    assert all(e.date.value is None for e in entries)
    assert all("no date" in " ".join(e.warnings) for e in entries)


def test_the_order_is_kept(bundle):
    paths = [e.source_path for e in get("telegram_voice").parse(bundle)]
    assert paths == [f"Telegram Voice Transcripts.md#{n:03d}" for n in (1, 2, 3)]


def test_the_length_of_each_recording_is_reported(bundle):
    first = list(get("telegram_voice").parse(bundle))[0]
    assert "14:16 long" in " ".join(first.warnings)


def test_a_clip_the_transcriber_doubted_says_so(bundle):
    last = list(get("telegram_voice").parse(bundle))[-1]
    assert any("near-empty clip" in w for w in last.warnings)


def test_a_plain_numbered_list_is_not_mistaken_for_transcripts(tmp_path):
    """The duration line is what distinguishes this format; numbered headings
    alone are just a document."""
    (tmp_path / "notes.md").write_text(
        "# Notes\n\n" + "\n\n".join(
            f"## {i}. Section {i}\n\nSome ordinary writing about the day and what happened in it."
            for i in range(1, 6)), encoding="utf-8")
    assert not any(d["adapter"] == "telegram_voice" for d in detect(Bundle(tmp_path)))
