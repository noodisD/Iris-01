"""Markdown markers come off when an entry is read, not when it is stored.

Fixtures are invented. Nothing here is anybody's journal.
"""

from agent.markdown_text import for_model, plain_text


def test_markers_become_the_words_they_were_around():
    md = "\n".join([
        "# Tomato soup",
        "",
        "> A **bold** _note_",
        "",
        "- [x] chop onions",
        "- simmer",
        "1. season",
        "",
        "See [the recipe](https://example.test/soup) and [[pot|stock]].",
        "Use `salt` and ~~pepper~~.",
    ])
    assert plain_text(md) == "\n".join([
        "Tomato soup",
        "",
        "A bold note",
        "",
        "chop onions",
        "simmer",
        "season",
        "",
        "See the recipe and stock.",
        "Use salt and pepper.",
    ])


def test_a_wiki_link_without_an_alias_keeps_its_name():
    assert plain_text("Stir [[stock]] gently.") == "Stir stock gently."


def test_a_code_fence_keeps_the_line_and_drops_the_fence():
    assert plain_text("```\nsalt\n```") == "\nsalt\n"


def test_an_underscore_inside_a_word_is_not_a_marker():
    assert plain_text("file_name stays") == "file_name stays"


def test_empty_input_is_empty():
    assert plain_text("") == ""
    assert plain_text(None) == ""


def test_plain_rows_are_not_stripped():
    assert for_model("salt * pepper", "plain") == "salt * pepper"
    assert for_model("salt * pepper", None) == "salt * pepper"


def test_markdown_rows_are_stripped_for_a_reader():
    assert for_model("**salt** and pepper", "markdown") == "salt and pepper"
