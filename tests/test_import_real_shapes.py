"""The owner's real export formats, with synthetic text.

The first run against real data found that none of the original six adapters
could read the owner's main journals: they live in the formats of earlier
personal projects (Elara, and an earlier IRIS), not Notion or Day One. It also
found two traps in those formats that these tests pin:

- The Elara export writes the day the *export* was made into each entry's
  `date` field. On the real archive, 80 of 89 entries read 2025-10-18. Trusting
  it would pile a year of writing onto one day.
- An earlier companion wrote its own "Breakthrough" notes into the owner's vault
  with dates in their filenames. Read as journal entries, a previous AI's
  conclusions would come back out of the engines as the owner's patterns.

The structures below are copied from the real files; every word of content is
invented.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from agent.importing import Bundle, detect, get
from agent.importing.service import ImportService

WORDS = "Slept badly again but got the deployment finished before lunch, which helped."


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


# --- earlier IRIS -----------------------------------------------------------

def _iris_og(tmp_path) -> Bundle:
    d = tmp_path / "iris_og"
    _write(d, "journal_entries.json", json.dumps([
        {"id": "a1", "date": "2025-11-07T20:50:07.141952", "date_readable": "Fri",
         "wellbeing": {"mood": 6, "energy": 5, "notes": "tired but fine"},
         "ideas": ["try pomodoro"], "goals": ["finish the course"], "execution": [],
         "reflections": WORDS, "created_at": "2025-11-07T20:50:07.14197"},
        {"id": "a2", "date": "2025-12-01T21:41:56", "preset_used": "evening",
         "wellbeing": {"mood": 7}, "ideas": [], "goals": [], "execution": [],
         "reflections": {"what_went_well": WORDS, "what_to_improve": "Start earlier.",
                         "key_insight": "Small steps work.", "tomorrow_priorities": "Gym."},
         "created_at": "2025-12-01T21:41:56"},
    ]))
    return Bundle(d)


def test_an_earlier_iris_journal_is_read_with_its_dates(tmp_path):
    bundle = _iris_og(tmp_path)
    assert detect(bundle)[0]["adapter"] == "iris_og_journal"

    entries = list(get("iris_og_journal").parse(bundle))
    assert [e.date.value for e in entries] == [date(2025, 11, 7), date(2025, 12, 1)]
    assert all(e.date.confidence == "certain" for e in entries)


def test_structured_reflections_keep_their_structure(tmp_path):
    """Later entries store reflections as named prompts. Run together they lose
    what each answer was an answer to."""
    second = list(get("iris_og_journal").parse(_iris_og(tmp_path)))[1]
    assert "What went well: " in second.content
    assert "Key insight: Small steps work." in second.content
    assert "Tomorrow's priorities: Gym." in second.content


def test_the_companions_copy_of_the_same_entries_is_not_read(tmp_path):
    """The earlier companion re-packaged the same entries with `text` instead of
    `reflections`. Reading both would count each entry twice, and the content
    hash cannot catch it because the two copies are not byte-identical."""
    d = tmp_path / "analysis"
    _write(d, "companion_analysis.json", json.dumps([
        {"message_id": "m1", "date": "2025-11-07", "text": WORDS, "source": "journal",
         "conversation_partner": "Self", "wellbeing": {"mood": 6}, "metadata": {}},
    ]))
    assert not any(d["adapter"] == "iris_og_journal" for d in detect(Bundle(d)))


# --- the Elara export -------------------------------------------------------

def _elara(tmp_path) -> Bundle:
    d = tmp_path / "elara"
    export_day = "2025-10-18"
    _write(d, "Journal.json", json.dumps({
        "metadata": {"total_entries": 3, "description": "Combined journal entries",
                     "date_range": {"earliest": "2024-07-18", "latest": export_day}},
        "entries": [
            {"id": 1, "filename": "Morning 2024-07-18 0123456789abcdef0123456789abcdef.md",
             "title": "Morning", "date": "2024-07-18", "tags": ["Daily"],
             "content": WORDS, "modified": "2024-07-18T08:00:00"},
            {"id": 2, "filename": "Routine 0123456789abcdef0123456789abcdef.md",
             "title": "Routine", "date": export_day, "tags": ["Daily\n\nMorning pages"],
             "content": "<aside>💡 **Notion Tip:** template text</aside>\n" + WORDS,
             "modified": f"{export_day}T08:35:54"},
            {"id": 3, "filename": "Gardening 0123456789abcdef0123456789abcdef.md",
             "title": "Gardening", "date": export_day, "tags": ["Work"],
             "content": WORDS + " Also a decent harvest.", "modified": f"{export_day}T08:35:54"},
        ],
    }))
    return Bundle(d)


def test_the_elara_export_is_recognised(tmp_path):
    assert detect(_elara(tmp_path))[0]["adapter"] == "elara_journal"


def test_a_filename_date_is_used(tmp_path):
    first = list(get("elara_journal").parse(_elara(tmp_path)))[0]
    assert first.date.value == date(2024, 7, 18)
    assert first.date.confidence == "certain"


def test_the_export_day_is_not_mistaken_for_when_an_entry_was_written(tmp_path):
    """The load-bearing test for this format. A `date` equal to the day the
    file was modified is the export stamping itself, and must come back as no
    date at all — with the reason — not as a year of entries on one day."""
    entries = list(get("elara_journal").parse(_elara(tmp_path)))
    stamped = entries[1:]
    assert all(e.date.value is None for e in stamped), [e.date for e in stamped]
    assert all("day the export was made" in " ".join(e.warnings) for e in stamped)
    assert date(2025, 10, 18) not in {e.date.value for e in entries}


def test_notion_boilerplate_and_broken_tags_are_dropped(tmp_path):
    second = list(get("elara_journal").parse(_elara(tmp_path)))[1]
    assert "Notion Tip" not in second.content
    assert second.tags == [], "the export's tags are unparsed Notion properties"


# --- notes an assistant wrote -----------------------------------------------

BREAKTHROUGH = """---
date: 2025-11-09
breakthrough_id: bt_42
category: realization
tags:
  - procrastination
---

# Breakthrough/realization detected

## The Breakthrough
Procrastination is a recurring challenge linked to fear of failure.
"""


def test_an_assistants_note_is_flagged_even_on_its_own(tmp_path):
    """Uploaded one file at a time there is no folder name to give it away, so
    the verdict has to come from the note itself."""
    d = tmp_path / "vault"
    _write(d, "2025-11-09 - Procrastination is a recurring challenge.md", BREAKTHROUGH)
    _write(d, "2025-11-10.md", WORDS + " A normal day, written by me.")
    entries = {e.source_path: e for e in get("dated_files").parse(Bundle(d))}

    flagged = entries["2025-11-09 - Procrastination is a recurring challenge.md"]
    assert flagged.likely_generated and "breakthrough_id" in flagged.likely_generated
    assert entries["2025-11-10.md"].likely_generated is None


def test_it_is_staged_excluded_with_the_reason_shown(tmp_path):
    """Excluded by default, never silently dropped — the owner can see it, see
    why, and include it anyway."""
    d = tmp_path / "vault"
    _write(d, "2025-11-09.md", BREAKTHROUGH)
    _write(d, "2025-11-10.md", WORDS)
    staged = [ImportService._to_item(e) for e in get("dated_files").parse(Bundle(d))]
    by_date = {str(i["entry_date"]): i for i in staged}

    assert by_date["2025-11-09"]["status"] == "excluded"
    assert any("assistant" in w for w in by_date["2025-11-09"]["warnings"])
    assert by_date["2025-11-10"]["status"] == "staged"


def test_ordinary_writing_about_insights_is_not_flagged(tmp_path):
    """The detector is deliberately narrow. A person writing about their own
    realisations must not be mistaken for an assistant."""
    d = tmp_path / "vault"
    _write(d, "2025-11-11.md",
           "# Why this matters\n\nI had an insight today about why I keep putting "
           "things off. Patterns identified: mornings are better.")
    entry = list(get("dated_files").parse(Bundle(d)))[0]
    assert entry.likely_generated is None
