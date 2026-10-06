"""A questionnaire the owner answers inside IRIS (ADR-0029).

The questions are someone else's writing and stay in a local data file
(`data/questionnaires/<name>.json`), never in the repository; this module only
knows their shape. The answers are the owner's: drafted here and sent nowhere
until the owner adds a section to IRIS. An added answer becomes a reflection
in the session format (ADR-0028): the question is a turn of its own, context
for a reader, and only the owner's turns can become evidence. Revising an
added answer keeps the earlier one as history and replaces its reflection.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from psycopg2.extras import Json

from . import sessions
from .config import settings
from .database import db

logger = logging.getLogger(__name__)

QUESTIONNAIRE = "baseline"
OWNER = "Me"
QUESTION = "Question"
IRIS = "IRIS"
_COLUMNS = ("id", "question_id", "version", "status", "answer", "transcript", "source",
            "reflection_id", "created_at", "updated_at", "added_at")


class QuestionnaireMissing(Exception):
    """The questionnaire's text is not on this machine."""


class QuestionnaireError(Exception):
    """Something the owner can put right, said so they can."""


def questionnaire_path(name: str = QUESTIONNAIRE) -> Path:
    return Path(settings.DATA_DIR) / "questionnaires" / f"{name}.json"


def load(name: str = QUESTIONNAIRE) -> dict | None:
    """The questionnaire as stored locally, or None when it is not installed."""
    path = questionnaire_path(name)
    if not path.exists():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    ids = [q["id"] for section in doc["sections"] for q in section["questions"]]
    if len(ids) != len(set(ids)):
        raise ValueError("questionnaire question ids repeat")
    return doc


def _iso(value) -> str | None:
    return value.isoformat() if value else None


class Questionnaires:
    def __init__(self, user_id: int, name: str = QUESTIONNAIRE):
        self.user_id = user_id
        self.name = name

    # --- reading ------------------------------------------------------------

    def _doc(self) -> dict:
        doc = load(self.name)
        if doc is None:
            raise QuestionnaireMissing("The questionnaire is not installed on this machine.")
        return doc

    def _question(self, doc: dict, question_id: str) -> tuple[dict, dict]:
        for section in doc["sections"]:
            for question in section["questions"]:
                if question["id"] == question_id:
                    return section, question
        raise LookupError("No such question.")

    def _versions(self, cur, question_id: str | None = None) -> dict[str, list[dict]]:
        cur.execute(f"""SELECT {', '.join(_COLUMNS)} FROM questionnaire_answers
                         WHERE user_id = %s AND questionnaire = %s
                           {'AND question_id = %s' if question_id else ''}
                         ORDER BY question_id, version DESC""",
                    (self.user_id, self.name, *([question_id] if question_id else [])))
        found: dict[str, list[dict]] = {}
        for row in cur.fetchall():
            item = dict(zip(_COLUMNS, row, strict=True))
            found.setdefault(item["question_id"], []).append(item)
        return found

    @staticmethod
    def _state(question: dict, versions: list[dict]) -> dict:
        latest = versions[0] if versions else None
        added = next((v for v in versions if v["status"] == "added"), None)
        status = latest["status"] if latest else "unanswered"
        return {
            "id": question["id"], "number": question["number"],
            "text": question["en"], "textPl": question["pl"],
            "status": status,
            "answer": latest["answer"] if latest and status in ("draft", "added") else "",
            "source": latest["source"] if latest else None,
            "transcript": latest["transcript"] if latest and status in ("draft", "added") else None,
            # A draft over an added answer is a revision waiting to be added.
            "revising": status == "draft" and added is not None,
            "addedAt": _iso(added["added_at"]) if added else None,
            "history": sum(v["status"] in ("added", "superseded") for v in versions),
        }

    def overview(self) -> dict:
        doc = self._doc()
        with db.connection() as conn, conn.cursor() as cur:
            versions = self._versions(cur)
        sections = []
        for section in doc["sections"]:
            questions = [self._state(q, versions.get(q["id"], [])) for q in section["questions"]]
            counts = {key: sum(q["status"] == key for q in questions)
                      for key in ("draft", "added", "skipped", "unanswered")}
            sections.append({"id": section["id"], "title": section["title_en"],
                             "titlePl": section["title_pl"], "intro": section["intro_en"],
                             "introPl": section["intro_pl"], "questions": questions,
                             "counts": {**counts, "total": len(questions)}})
        return {"id": doc["id"], "title": doc["title_en"], "titlePl": doc["title_pl"],
                "version": doc.get("version"), "about": doc.get("about_en"),
                "aboutPl": doc.get("about_pl"), "sections": sections}

    def question(self, question_id: str) -> dict:
        doc = self._doc()
        _, question = self._question(doc, question_id)
        with db.connection() as conn, conn.cursor() as cur:
            versions = self._versions(cur, question_id).get(question_id, [])
        return self._state(question, versions)

    def history(self, question_id: str) -> list[dict]:
        """Every answer that was added to IRIS, newest first."""
        self._question(self._doc(), question_id)
        with db.connection() as conn, conn.cursor() as cur:
            versions = self._versions(cur, question_id).get(question_id, [])
        return [{"version": v["version"], "answer": v["answer"], "source": v["source"],
                 "status": v["status"], "addedAt": _iso(v["added_at"])}
                for v in versions if v["status"] in ("added", "superseded")]

    # --- drafting -------------------------------------------------------------

    def save(self, question_id: str, answer: str, source: str = "form",
             transcript: list | None = None) -> dict:
        """Keep a draft answer. Nothing is sent anywhere."""
        if source not in ("form", "interview", "suggested"):
            raise QuestionnaireError("Unknown answer source.")
        self._question(self._doc(), question_id)
        text = (answer or "").strip()
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(73201, %s)", (self.user_id,))
            versions = self._versions(cur, question_id).get(question_id, [])
            latest = versions[0] if versions else None
            quotes = ((latest.get("transcript") or {}).get("quotes") or []) \
                if latest and latest["source"] == "suggested" and isinstance(latest.get("transcript"), dict) else []
            if source == "form" and any(quote in text for quote in quotes):
                # Still the owner's earlier sentences, quoted: still a suggestion,
                # so it does not count twice as evidence (ADR-0029).
                source, transcript = "suggested", latest["transcript"]
            if latest and latest["status"] in ("draft", "skipped"):
                if not text:
                    cur.execute("DELETE FROM questionnaire_answers WHERE id = %s", (latest["id"],))
                else:
                    cur.execute("""UPDATE questionnaire_answers
                                      SET status = 'draft', answer = %s, source = %s, transcript = %s,
                                          updated_at = NOW() WHERE id = %s""",
                                (text, source, Json(transcript) if transcript else None, latest["id"]))
            elif text and not (latest and latest["status"] == "added" and latest["answer"] == text):
                cur.execute("""INSERT INTO questionnaire_answers
                                   (user_id, questionnaire, question_id, version, status, answer,
                                    source, transcript)
                               VALUES (%s, %s, %s, %s, 'draft', %s, %s, %s)""",
                            (self.user_id, self.name, question_id,
                             (latest["version"] if latest else 0) + 1, text, source,
                             Json(transcript) if transcript else None))
            conn.commit()
        return self.question(question_id)

    def skip(self, question_id: str, skipped: bool) -> dict:
        """Mark a question as one the owner chose not to answer, or take that back."""
        self._question(self._doc(), question_id)
        with db.connection() as conn, conn.cursor() as cur:
            versions = self._versions(cur, question_id).get(question_id, [])
            latest = versions[0] if versions else None
            if skipped and not (latest and latest["status"] == "skipped"):
                if latest and latest["status"] == "draft":
                    cur.execute("""UPDATE questionnaire_answers SET status = 'skipped', answer = '',
                                          transcript = NULL, updated_at = NOW() WHERE id = %s""",
                                (latest["id"],))
                else:
                    cur.execute("""INSERT INTO questionnaire_answers
                                       (user_id, questionnaire, question_id, version, status)
                                   VALUES (%s, %s, %s, %s, 'skipped')""",
                                (self.user_id, self.name, question_id,
                                 (latest["version"] if latest else 0) + 1))
            elif not skipped and latest and latest["status"] == "skipped":
                cur.execute("DELETE FROM questionnaire_answers WHERE id = %s", (latest["id"],))
            conn.commit()
        return self.question(question_id)

    # --- adding to IRIS ---------------------------------------------------------

    def _drafts(self, cur, doc: dict, section_id: str) -> list[tuple[dict, dict, dict | None]]:
        """(question, draft, the added version it replaces) for a section's drafts."""
        section = next((s for s in doc["sections"] if s["id"] == section_id), None)
        if section is None:
            raise LookupError("No such section.")
        versions = self._versions(cur)
        out = []
        for question in section["questions"]:
            rows = versions.get(question["id"], [])
            if rows and rows[0]["status"] == "draft" and rows[0]["answer"].strip():
                out.append((question, rows[0], next((v for v in rows if v["status"] == "added"), None)))
        return out

    @staticmethod
    def content(question: dict, draft: dict, on: date) -> str:
        """The reflection an answer becomes: the question, then the owner's words."""
        # A suggestion keeps its quotes as {"quotes": [...]}; only an interview has turns.
        raw = draft.get("transcript") if isinstance(draft.get("transcript"), list) else []
        transcript = [turn for turn in raw if (turn.get("text") or "").strip()]
        said = [turn["text"].strip() for turn in transcript if turn.get("role") == "owner"]
        if draft["source"] == "interview" and said and "\n\n".join(said) == draft["answer"]:
            # The whole exchange: what IRIS asked is context, every reply the
            # owner's own words.
            found = [sessions.Segment(0, IRIS if turn["role"] == "iris" else OWNER, turn["text"].strip())
                     for turn in transcript]
            asker = IRIS
        else:
            # A form answer, or an interview answer edited afterwards: the
            # question as asked, then the answer as the owner left it.
            found = [sessions.Segment(0, QUESTION, question["en"]),
                     sessions.Segment(0, OWNER, draft["answer"])]
            asker = QUESTION
        language = sessions.guess_language(draft["answer"])
        return sessions.compose(found, kind="questionnaire", started=f"{on.isoformat()}T00:00",
                                language=language, owner=OWNER, asker=asker, question=question["id"])

    def estimate(self, section_id: str) -> dict:
        """What adding a section sends and costs, worked out without sending anything."""
        from .discovery import update_estimate
        from .episodes import SYSTEM_PROMPT as READ_PROMPT
        from .intelligence import Intelligence

        doc = self._doc()
        with db.connection() as conn, conn.cursor() as cur:
            drafts = self._drafts(cur, doc, section_id)
        model, tier = settings.OPENAI_WORKER_MODEL, settings.OPENAI_WORKER_SERVICE_TIER or None
        price = Intelligence.PRICE_PER_MTOK.get(model)
        factor = Intelligence.TIER_PRICE_FACTOR.get(tier or "", 1.0)
        if not drafts or not price:
            return {"answers": len(drafts), "dollars": None, "text": ""}
        chars = sum(len(sessions.for_model(self.content(q, d, date.today()))) for q, d, _ in drafts)
        # One reading per answer and a field check for what it finds, then one
        # update of patterns for the whole section.
        tokens_in = (len(drafts) * (len(READ_PROMPT) + 3000) + chars) // 3
        tokens_out = len(drafts) * 1500
        _, update_in, update_out = update_estimate(self.user_id, len(drafts), len(drafts) // 3)
        dollars = ((tokens_in + update_in) * price[0] + (tokens_out + update_out) * price[1]) \
            / 1_000_000 * factor
        return {"answers": len(drafts), "dollars": round(dollars, 3),
                "text": (f"Adding {len(drafts)} answer{'' if len(drafts) == 1 else 's'} sends "
                         f"{'it' if len(drafts) == 1 else 'them'} to OpenAI to be indexed for chat "
                         f"and read for patterns, then updates your patterns: at most about ${dollars:.2f}.")}

    def add_section(self, section_id: str) -> dict:
        """The owner's click: a section's drafts become reflections IRIS reads."""
        doc = self._doc()
        today = date.today()
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(73201, %s)", (self.user_id,))
            drafts = self._drafts(cur, doc, section_id)
            conn.commit()
        added = 0
        for question, draft, replaced in drafts:
            reflection_id = db.create_reflection(
                self.user_id, self.content(question, draft, today), reflection_date=today,
                source="questionnaire", content_format="session",
                date_source="user", date_confidence="certain",
                # A suggestion is the owner's sentences quoted from entries that
                # already count: memory for chat, not evidence a second time.
                evidence_eligible=draft["source"] != "suggested")
            with db.connection() as conn, conn.cursor() as cur:
                cur.execute("""UPDATE questionnaire_answers
                                  SET status = 'added', reflection_id = %s, added_at = NOW(),
                                      updated_at = NOW() WHERE id = %s""", (reflection_id, draft["id"]))
                if replaced:
                    cur.execute("""UPDATE questionnaire_answers SET status = 'superseded',
                                          updated_at = NOW() WHERE id = %s""", (replaced["id"],))
                conn.commit()
            if replaced and replaced["reflection_id"]:
                db.delete_reflection(replaced["reflection_id"])
            added += 1
        if added:
            from .importing.service import _kick_the_queue
            _kick_the_queue()
        logger.info(f"Questionnaire section {section_id}: {added} answers added")
        return {"added": added}

    # --- suggestions from the owner's own writing --------------------------------

    def _unanswered(self, doc: dict, section_id: str) -> list[dict]:
        section = next((s for s in doc["sections"] if s["id"] == section_id), None)
        if section is None:
            raise LookupError("No such section.")
        with db.connection() as conn, conn.cursor() as cur:
            versions = self._versions(cur)
        return [q for q in section["questions"] if not versions.get(q["id"])]

    def suggest_estimate(self, section_id: str) -> dict:
        """What suggesting answers for a section's empty questions sends and costs."""
        from .intelligence import Intelligence
        from .questionnaire_suggest import ENTRY_CHARS, PROMPT, SOURCES_PER_QUESTION

        questions = self._unanswered(self._doc(), section_id)
        price = Intelligence.PRICE_PER_MTOK.get(settings.OPENAI_WORKER_MODEL)
        if not questions or not price:
            return {"questions": len(questions), "dollars": None, "text": ""}
        tokens_in = len(questions) * (len(PROMPT) + SOURCES_PER_QUESTION * ENTRY_CHARS) // 3
        dollars = (tokens_in * price[0] + len(questions) * 600 * price[1]) / 1_000_000
        return {"questions": len(questions), "dollars": round(dollars, 3),
                "text": (f"Looks through your journal, sessions and chat for the {len(questions)} empty "
                         f"question{'' if len(questions) == 1 else 's'}: the most related passages are sent "
                         f"to OpenAI, about ${max(dollars, 0.01):.2f}. Suggestions are your own sentences, "
                         "quoted; nothing is added until you add the section.")}

    def suggest_section(self, section_id: str, intelligence) -> dict:
        """Suggested drafts for a section's empty questions, from the owner's own writing."""
        from .questionnaire_suggest import draft, suggest_all

        questions = self._unanswered(self._doc(), section_id)
        results = suggest_all(questions, self.user_id, intelligence)
        suggested = nothing = failed = 0
        for question in questions:
            quotes = results[question["id"]]
            if quotes is None:
                failed += 1
                continue
            if not quotes:
                nothing += 1
                continue
            with db.connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(73201, %s)", (self.user_id,))
                if self._versions(cur, question["id"]).get(question["id"]):
                    conn.commit()
                    continue  # the owner wrote something meanwhile; theirs stands
                cur.execute("""INSERT INTO questionnaire_answers
                                   (user_id, questionnaire, question_id, version, status, answer,
                                    source, transcript)
                               VALUES (%s, %s, %s, 1, 'draft', %s, 'suggested', %s)""",
                            (self.user_id, self.name, question["id"], draft(quotes),
                             Json({"quotes": [q["text"] for q in quotes]})))
                conn.commit()
            suggested += 1
        logger.info(f"Questionnaire section {section_id}: {suggested} suggested, {nothing} nothing found, "
                    f"{failed} failed")
        return {"suggested": suggested, "nothing": nothing, "failed": failed}
