"""A recorded conversation, kept as its speakers said it (ADR-0028).

A therapy session is not a journal entry. Two people speak in it and only one
of them is the owner, while everything IRIS concludes has to stand on the
owner's own words. So a session is stored with who said each turn, and every
reader that turns writing into evidence asks this module which words are the
owner's.

The stored text carries that itself, so whoever holds an entry's content can
tell whose words a span is without looking anything else up:

    ---
    session: therapy
    started: 2026-09-30T18:00
    language: pl
    owner: Ann
    therapist: Counsellor
    ---

    **[00:00:05] Ann:**
    the words, as transcribed

    **[00:00:31] Counsellor:**
    the words, as transcribed

A turn is one speaker's uninterrupted stretch: consecutive transcript segments
under the same label are joined into one. Its role comes from its label alone.
Exactly the owner's label is the owner; exactly the therapist's label is the
therapist; anything else, including a label the transcript marks as uncertain,
is unclear. Only the owner's turns can be evidence. The therapist's turns and
the unclear ones are context: a reader is shown them, labelled, and nothing
they say is ever quoted as the owner's.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FORMAT = "session"
KINDS = ("therapy", "questionnaire")
ROLES = ("owner", "therapist", "asker", "unclear")

#: How much of a session one recalled passage holds. Small enough that a
#: memory names one moment of the conversation, large enough to keep a
#: question together with its answer.
PASSAGE_CHARS = 700

#: A transcript turn: "**[00:01:02] Name:**", the words on the following lines
#: or after the marker. Hours are optional and bold is optional, so the
#: "[01:02] Name: words" lines most transcribers write are read as well.
_HEADER = re.compile(
    r"^(?:\*\*)?\[(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\][ \t]+([^:*\[\]\n]{1,60}?)[ \t]*:"
    r"(?:\*\*)?[ \t]*(.*)$", re.M)
_FENCE = "---"
_ROLE_WORDS = {"owner": "owner", "therapist": "therapist", "asker": "question",
               "unclear": "speaker unclear"}
_LANGUAGES = {"pl": "Polish", "en": "English", "de": "German", "es": "Spanish",
              "fr": "French", "it": "Italian", "uk": "Ukrainian"}
#: A label the transcriber was not sure of. Only a default for the owner's
#: choice on the import screen; a role is never read from these words.
_UNSURE = re.compile(r"niepewn|unsure|uncertain|unclear|unknown|nieznan|\?", re.I)
_THERAPIST = re.compile(r"terapeut|therapist|psycholog|counsel", re.I)
_POLISH_LETTERS = re.compile(r"[ąćęłńóśźż]", re.I)
_LETTERS = re.compile(r"[^\W\d_]", re.UNICODE)


@dataclass(frozen=True)
class Segment:
    """One labelled stretch of an uploaded transcript, before turns are joined."""

    at: int
    label: str
    text: str


@dataclass(frozen=True)
class Turn:
    """One speaker's uninterrupted stretch, and where its words sit in the content."""

    at: int
    label: str
    role: str
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class Session:
    kind: str
    started: str | None
    language: str | None
    owner: str | None
    therapist: str | None
    turns: tuple[Turn, ...]
    #: A questionnaire answer: who asked (the question or IRIS), and which question.
    asker: str | None = None
    question: str | None = None

    @property
    def duration(self) -> int | None:
        """Seconds to the last turn's start: the recording's length, near enough."""
        return self.turns[-1].at if self.turns else None


@dataclass(frozen=True)
class Passage:
    """Consecutive turns recalled together, each line saying who spoke."""

    position: int
    at: int
    text: str


def clock(seconds: int) -> str:
    hours, rest = divmod(max(0, int(seconds)), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _seconds(hours: str | None, minutes: str, secs: str) -> int:
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(secs)


# --- an uploaded transcript --------------------------------------------------

def segments(text: str) -> tuple[list[Segment], int]:
    """The transcript's labelled segments, and how many lines came before the first.

    Lines before the first turn are the transcriber's title and notes: nobody
    said them, so they are left out and counted for the owner to see. A turn
    marker with no words under it is dropped.
    """
    found: list[Segment] = []
    marks = list(_HEADER.finditer(text or ""))
    if not marks:
        return [], 0
    preamble = sum(1 for line in text[:marks[0].start()].splitlines() if line.strip())
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        words = " ".join(line.strip() for line in
                         [mark.group(5), *text[mark.end():end].splitlines()] if line.strip())
        if words:
            found.append(Segment(at=_seconds(*mark.group(1, 2, 3)), label=mark.group(4).strip(),
                                 text=words))
    return found, preamble


def relabel_segments(text: str, labels: list[str]) -> str:
    """The transcript with each segment's speaker label replaced, and nothing else.

    `labels` lines up with `segments(text)`: one per segment that has words.
    Only the label inside each turn marker changes; times, words and layout
    stay as they were.
    """
    marks = list(_HEADER.finditer(text or ""))
    spoken = [mark for index, mark in enumerate(marks)
              if mark.group(5).strip() or text[mark.end():marks[index + 1].start()
                                               if index + 1 < len(marks) else len(text)].strip()]
    if len(spoken) != len(labels):
        raise ValueError("one label is needed for every segment")
    out, last = [], 0
    for mark, label in zip(spoken, labels):
        if "\n" in label or ":" in label or not label.strip():
            raise ValueError("a speaker label is one line without a colon")
        out += [text[last:mark.start(4)], label]
        last = mark.end(4)
    out.append(text[last:])
    return "".join(out)


def speakers(found: list[Segment]) -> list[dict]:
    """Every label, with how many segments and words it holds, most words first."""
    tally: dict[str, dict] = {}
    for segment in found:
        row = tally.setdefault(segment.label, {"label": segment.label, "segments": 0, "words": 0})
        row["segments"] += 1
        row["words"] += len(segment.text.split())
    return sorted(tally.values(), key=lambda row: (-row["words"], row["label"]))


def guess_roles(found: list[Segment]) -> tuple[str | None, str | None]:
    """A starting choice of (owner, therapist) labels for the owner to confirm.

    A label that names a therapist is the therapist; of the labels left that
    are not marked uncertain, the one with the most words is offered as the
    owner, since a client usually talks more than their therapist. Nothing
    reads these guesses as decided: a session cannot be imported until the
    owner has looked at them.
    """
    sure = [row["label"] for row in speakers(found) if not _UNSURE.search(row["label"])]
    therapist = next((label for label in sure if _THERAPIST.search(label)), None)
    owner = next((label for label in sure if label != therapist), None)
    if therapist is None:
        therapist = next((label for label in sure if label != owner), None)
    return owner, therapist


def guess_language(text: str) -> str:
    letters = len(_LETTERS.findall(text or ""))
    return "pl" if letters and len(_POLISH_LETTERS.findall(text)) / letters > 0.005 else "en"


def compose(found: list[Segment], *, kind: str, started: str, language: str,
            owner: str, therapist: str | None = None, asker: str | None = None,
            question: str | None = None) -> str:
    """The stored session: the speakers named, then one paragraph per turn.

    Words are kept exactly as transcribed; only layout changes, where
    consecutive segments by one speaker become one turn.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown session kind: {kind!r}")
    values = {"session": kind, "started": started, "language": language,
              "owner": owner, "therapist": therapist or "", "asker": asker or "",
              "question": question or ""}
    for key, value in values.items():
        if "\n" in value or (key not in ("therapist", "asker", "question") and not value.strip()):
            raise ValueError(f"session {key} must be one non-empty line")
    turns: list[Segment] = []
    for segment in found:
        if turns and turns[-1].label == segment.label:
            turns[-1] = Segment(turns[-1].at, segment.label, f"{turns[-1].text} {segment.text}")
        else:
            turns.append(segment)
    head = [_FENCE, *(f"{key}: {value.strip()}" for key, value in values.items() if value.strip()), _FENCE]
    body = [f"**[{clock(turn.at)}] {turn.label}:**\n{turn.text}" for turn in turns]
    return "\n".join(head) + "\n\n" + "\n\n".join(body) + "\n"


# --- a stored session --------------------------------------------------------

def read(content: str | None) -> Session | None:
    """The stored session, or None when the content is not one."""
    text = content or ""
    if not text.startswith(_FENCE + "\n"):
        return None
    close = text.find("\n" + _FENCE + "\n", len(_FENCE))
    if close < 0:
        return None
    meta: dict[str, str] = {}
    for line in text[len(_FENCE) + 1:close].splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip().lower()] = value.strip()
    if meta.get("session") not in KINDS:
        return None
    owner, therapist = meta.get("owner") or None, meta.get("therapist") or None
    asker = meta.get("asker") or None
    body = close + len(_FENCE) + 2
    marks = list(_HEADER.finditer(text, body))
    turns: list[Turn] = []
    for index, mark in enumerate(marks):
        start = mark.start(5) if mark.group(5).strip() else mark.end()
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        region = text[start:end]
        lead = len(region) - len(region.lstrip())
        words = region.strip()
        if not words:
            continue
        label = mark.group(4).strip()
        role = ("owner" if owner and label == owner else
                "therapist" if therapist and label == therapist else
                "asker" if asker and label == asker else "unclear")
        turns.append(Turn(at=_seconds(*mark.group(1, 2, 3)), label=label, role=role, text=words,
                          start=start + lead, end=start + lead + len(words)))
    return Session(kind=meta["session"], started=meta.get("started") or None,
                   language=meta.get("language") or None, owner=owner, therapist=therapist,
                   turns=tuple(turns), asker=asker, question=meta.get("question") or None)


def _line(turn: Turn) -> str:
    return f"[{clock(turn.at)}] {turn.label} ({_ROLE_WORDS[turn.role]}): {turn.text}"


def describe(session: Session) -> str:
    """One sentence saying what the session is, for a reader that sees no turns."""
    language = _LANGUAGES.get(session.language or "", session.language)
    when = session.started.replace("T", " at ") if session.started else None
    counted = {role: sum(turn.role == role for turn in session.turns) for role in ROLES}
    if session.kind == "questionnaire":
        # Not a conversation that happened: the owner answering one question of
        # their baseline questionnaire, in writing or in a short interview.
        return ("The owner's answer to one question of their baseline questionnaire"
                + (f", given {session.started.split('T')[0]}" if session.started else "")
                + ". Turns marked question are what was asked, and context; only turns marked "
                "owner are the owner's words.")
    parts = [f"A {session.kind} session"
             + (f", recorded {when}" if when else "")
             + (f", about {round(session.duration / 60)} minutes" if session.duration else "")
             + (f", transcribed in {language}" if language else "") + "."]
    names = []
    if session.owner:
        names.append(f"{session.owner} is the owner ({counted['owner']} turns)")
    if session.therapist:
        names.append(f"{session.therapist} is the therapist ({counted['therapist']} turns)")
    if names:
        parts.append(" ".join(["Speakers:", "; ".join(names) + "."]))
    if counted["unclear"]:
        parts.append(f"{counted['unclear']} turns have no certain speaker and could be either.")
    return " ".join(parts)


def for_model(content: str | None) -> str:
    """The session as a model reads it: who is who, then every turn labelled."""
    session = read(content)
    if session is None:
        return content or ""
    return describe(session) + "\n\n" + "\n".join(_line(turn) for turn in session.turns)


def owner_turn(content: str | None, quote: str) -> tuple[Turn, str] | None:
    """The owner's turn that holds this quote, and the quote as written there.

    Searched in the owner's turns only, so words the therapist also said do not
    count, and a quote that runs across another speaker's turn is in none.
    """
    from .readable import locate

    session = read(content)
    if session is None:
        return None
    for turn in session.turns:
        if turn.role == "owner" and (span := locate(turn.text, quote)) is not None:
            return turn, span
    return None


def around(content: str | None, quote: str, before: int = 2, after: int = 1) -> str | None:
    """The owner's turn holding the quote with the turns either side, labelled.

    Context for a judgment about one quote: the question the owner was
    answering matters, the other fifty minutes do not.
    """
    session = read(content)
    held = owner_turn(content, quote)
    if session is None or held is None:
        return None
    index = session.turns.index(held[0])
    shown = session.turns[max(0, index - before):index + after + 1]
    return "\n".join(_line(turn) for turn in shown)


def owner_words(content: str | None) -> str:
    """Everything the owner said in the session, turn by turn, and nothing else."""
    session = read(content)
    if session is None:
        return ""
    return "\n\n".join(turn.text for turn in session.turns if turn.role == "owner")


def passages(content: str | None, limit: int = PASSAGE_CHARS) -> list[Passage]:
    """The session cut into recall-sized runs of whole turns, labelled.

    A turn is never split, so a recalled passage never shows words without
    the speaker who said them. One long turn is a passage on its own.
    """
    session = read(content)
    if session is None:
        return []
    found: list[Passage] = []
    lines: list[str] = []
    at = 0
    for turn in session.turns:
        line = _line(turn)
        if lines and sum(len(item) + 1 for item in lines) + len(line) > limit:
            found.append(Passage(position=len(found), at=at, text="\n".join(lines)))
            lines = []
        if not lines:
            at = turn.at
        lines.append(line)
    if lines:
        found.append(Passage(position=len(found), at=at, text="\n".join(lines)))
    return found
