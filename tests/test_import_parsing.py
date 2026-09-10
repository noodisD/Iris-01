"""Reading an export: formats, dates, and refusing to guess.

These are deliberately database-free and network-free. They build a fixture
directory, hand it to an adapter, and check what comes back.

The load-bearing test in this file is the one asserting that an entry whose date
cannot be determined comes back with no date at all. `reflection_date` becomes
`occurred_at` for every analytical window, so a guessed date is not a small
inaccuracy in one row — it is a wrong answer everywhere, and a silent one.
"""

from __future__ import annotations

import json
import zipfile
from datetime import date
from pathlib import Path

import pytest

from agent.importing import Bundle, UnsafeArchive, detect, extract_safely, get
from agent.importing.dates import parse_date_text

ENTRY = ("Spent most of the morning in the garden. The gate has been sticking "
         "since spring and I finally took it off its hinges and planed the edge.")


# --- fixtures ---------------------------------------------------------------

def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def notion(tmp_path):
    d = tmp_path / "notion"
    for i, day in enumerate(("March 1, 2024", "March 2, 2024", "March 3, 2024"), 1):
        _write(d, f"Journal {i} {'a' * 24}{i:08d}.md",
               f"# Journal {i}\n\nCreated: {day}\nTags: calm, garden\n\n{ENTRY} ({i})\n")
    return Bundle(d)


@pytest.fixture
def dayone(tmp_path):
    d = tmp_path / "dayone"
    _write(d, "Journal.json", json.dumps({
        "metadata": {"version": "1.0"},
        "entries": [
            {"uuid": "A1", "creationDate": "2024-03-01T07:12:00Z", "text": ENTRY,
             "tags": ["garden"]},
            {"uuid": "B2", "creationDate": "2024-03-05T19:40:00Z",
             "text": "Long call with my sister about the move to Lisbon."},
        ],
    }))
    return Bundle(d)


@pytest.fixture
def dated_files(tmp_path):
    d = tmp_path / "dated"
    for day in ("2024-03-01", "2024-03-02", "2024-03-03"):
        _write(d, f"{day}.md", f"{ENTRY}\n\nWritten on {day}.\n")
    return Bundle(d)


@pytest.fixture
def single_file(tmp_path):
    d = tmp_path / "single"
    body = "\n\n".join(
        f"# 2024-03-0{i}\n\n{ENTRY} Day {i}, with rather more text so the file "
        f"is comfortably past the size floor the sniffer uses."
        for i in range(1, 5)
    )
    _write(d, "journal.md", body)
    return Bundle(d)


@pytest.fixture
def csv_table(tmp_path):
    d = tmp_path / "csv"
    rows = "\n".join(f'2024-03-0{i},"{ENTRY} Row {i}"' for i in range(1, 5))
    _write(d, "export.csv", f"Created,Note\n{rows}\n")
    return Bundle(d)


ALL = ("notion", "dayone", "dated_files", "single_file", "csv_table")


# --- detection --------------------------------------------------------------

@pytest.mark.parametrize("fixture_name,expected", [
    ("notion", "notion"), ("dayone", "dayone"), ("dated_files", "dated_files"),
    ("single_file", "single_file"), ("csv_table", "csv_table"),
])
def test_each_export_is_recognised_as_itself(request, fixture_name, expected):
    """The sniff matrix. This is what protects the registry as adapters are
    added: a new one that scores highly on someone else's export breaks it."""
    bundle = request.getfixturevalue(fixture_name)
    found = detect(bundle)
    assert found, f"nothing recognised the {fixture_name} fixture"
    assert found[0]["adapter"] == expected, (
        f"{fixture_name} was read as {found[0]['adapter']}: {found}"
    )


def test_an_unrecognised_export_still_gets_a_reader(tmp_path):
    """An export from a tool nobody anticipated must degrade to "every file is
    an entry, check the dates", not to a failure."""
    d = tmp_path / "mystery"
    _write(d, "some thoughts.md", ENTRY)
    _write(d, "more thoughts.md", ENTRY + " And then some more.")
    found = detect(Bundle(d))
    assert found[0]["adapter"] == "plain_files"


# --- parsing ----------------------------------------------------------------

def test_notion_reads_the_date_out_of_its_property_block(notion):
    entries = list(get("notion").parse(notion))
    assert len(entries) == 3
    assert {e.date.value for e in entries} == {
        date(2024, 3, 1), date(2024, 3, 2), date(2024, 3, 3)
    }
    assert all(e.date.confidence == "certain" for e in entries)
    first = entries[0]
    assert "Created:" not in first.content, "properties are metadata, not writing"
    assert "Journal 1" == first.title
    assert "garden" in first.tags


def test_dayone_reads_creation_dates(dayone):
    entries = list(get("dayone").parse(dayone))
    assert [e.date.value for e in entries] == [date(2024, 3, 1), date(2024, 3, 5)]
    assert entries[0].date.source == "json_field"
    assert entries[0].tags == ["garden"]


def test_dated_filenames_are_read(dated_files):
    entries = list(get("dated_files").parse(dated_files))
    assert {e.date.value for e in entries} == {
        date(2024, 3, 1), date(2024, 3, 2), date(2024, 3, 3)
    }


def test_one_file_splits_at_its_date_headings(single_file):
    entries = list(get("single_file").parse(single_file))
    assert len(entries) == 4
    assert entries[0].date.value == date(2024, 3, 1)
    assert "Day 1" in entries[0].content
    assert "Day 2" not in entries[0].content, "sections must not bleed into each other"


def test_csv_finds_the_date_and_the_prose_column(csv_table):
    entries = list(get("csv_table").parse(csv_table))
    assert len(entries) == 4
    assert entries[0].date.value == date(2024, 3, 1)
    assert "Row 1" in entries[0].content


def test_frontmatter_beats_the_filename(tmp_path):
    """A date the exporting tool wrote deliberately is better evidence than one
    that happens to be in a filename."""
    d = tmp_path / "fm"
    _write(d, "2024-01-01.md", f"---\ndate: 2024-03-09\n---\n\n{ENTRY}\n")
    entry = list(get("dated_files").parse(Bundle(d)))[0]
    assert entry.date.value == date(2024, 3, 9)
    assert entry.date.source == "frontmatter"
    assert "---" not in entry.content, "front matter is metadata, not writing"


def test_a_directory_layout_can_carry_the_date(tmp_path):
    d = tmp_path / "tree"
    _write(d, "2024/03/01.md", ENTRY)
    _write(d, "2024/03/02.md", ENTRY + " More.")
    entries = list(get("dated_files").parse(Bundle(d)))
    assert {e.date.value for e in entries} == {date(2024, 3, 1), date(2024, 3, 2)}


# --- the rule the whole feature rests on ------------------------------------

def test_a_date_that_cannot_be_determined_is_left_empty(tmp_path):
    """No fallback to today. No fallback to the file's modification time.

    Either the date was stated somewhere, or a human resolves it. Anything else
    puts an entry in the wrong analytical window with nothing to show for it.
    """
    d = tmp_path / "undated"
    _write(d, "some thoughts.md", ENTRY)
    entry = list(get("plain_files").parse(Bundle(d)))[0]

    assert entry.date.value is None
    assert entry.date.confidence == "unknown"
    assert entry.date.source == "unknown"


def test_an_ambiguous_date_says_so_rather_than_picking_silently():
    guess = parse_date_text("03/04/2024")
    assert guess.confidence == "probable"
    assert guess.note and "March" in guess.note and "April" in guess.note


def test_an_unambiguous_day_first_date_is_certain():
    """25/03/2024 has only one reading, because there is no 25th month."""
    guess = parse_date_text("25/03/2024")
    assert guess.value == date(2024, 3, 25)
    assert guess.confidence == "certain"


def test_impossible_dates_are_rejected_not_clamped():
    assert parse_date_text("2024-13-01").value is None
    assert parse_date_text("2024-02-30").value is None


def test_a_number_that_is_not_a_date_is_not_read_as_one():
    assert parse_date_text("invoice 12345678 final").value is None
    assert parse_date_text("no date here at all").value is None


# --- archives ---------------------------------------------------------------

def _zip(path: Path, members: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return path


def test_a_normal_export_zip_extracts(tmp_path):
    src = _zip(tmp_path / "ok.zip", {"a/2024-03-01.md": ENTRY, "a/b/2024-03-02.md": ENTRY})
    result = extract_safely(src, tmp_path / "out")
    assert result.file_count == 2
    assert {f.rel_path for f in Bundle(result.root).files()} == {
        "a/2024-03-01.md", "a/b/2024-03-02.md"
    }


def test_path_traversal_is_refused(tmp_path):
    src = _zip(tmp_path / "evil.zip", {"../../etc/passwd": "root:x:0:0"})
    with pytest.raises(UnsafeArchive, match="traversal"):
        extract_safely(src, tmp_path / "out")
    assert not (tmp_path.parent / "etc").exists()


def test_an_absolute_path_is_refused(tmp_path):
    src = _zip(tmp_path / "abs.zip", {"/etc/passwd": "root:x:0:0"})
    with pytest.raises(UnsafeArchive):
        extract_safely(src, tmp_path / "out")


def test_a_symlink_member_is_refused(tmp_path):
    """The hole ZipFile.extract leaves open: `..` is sanitised, a symlink is
    not, and the next member written through it lands wherever it points."""
    src = tmp_path / "link.zip"
    with zipfile.ZipFile(src, "w") as zf:
        info = zipfile.ZipInfo("escape")
        info.external_attr = (0o120777 << 16)      # symlink
        zf.writestr(info, "/etc/passwd")
    with pytest.raises(UnsafeArchive, match="symlink"):
        extract_safely(src, tmp_path / "out")


def test_a_zip_bomb_is_refused_before_anything_is_written(tmp_path):
    src = tmp_path / "bomb.zip"
    with zipfile.ZipFile(src, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("big.txt", "0" * (8 * 1024 * 1024))
    out = tmp_path / "out"
    with pytest.raises(UnsafeArchive, match="zip bomb"):
        extract_safely(src, out)
    assert not any(out.rglob("*.txt")), "nothing should have been written"


def test_bundle_ignores_the_noise_an_export_carries(tmp_path):
    d = tmp_path / "noisy"
    _write(d, "2024-03-01.md", ENTRY)
    _write(d, ".DS_Store", "junk")
    _write(d, "__MACOSX/._2024-03-01.md", "junk")
    assert {f.rel_path for f in Bundle(d).files()} == {"2024-03-01.md"}
