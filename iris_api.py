"""
IRIS HTTP API — the web app's backend, for one local user with no login
(ADR-0001), bound to loopback. It serves the built SPA from the same process
that stores the data. The CLI (companion.py) is the same product through a
terminal and resolves the same user.
"""

import logging

from agent.logging_config import configure_logging

# Configure logging first, before any other imports
configure_logging()
# Named explicitly: as __main__ this logger would miss the handlers that
# configure_logging() attaches to "iris_api".
logger = logging.getLogger("iris_api")

import hashlib
import json
import os
import re
import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from typing import Literal

from pydantic import BaseModel, Field
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool

# Load environment variables
load_dotenv()

# Import the companion system
try:
    from agent.constants import OBSERVATION_MAX_ENTRIES_READ, SELECTABLE_ENGINES
    from agent.core import PersonalAICompanion
    from agent.database import db
    from agent.insights_service import InsightsService
    from agent.observations import ObservationEngine, apply_preferences
    from agent import constructs
    from agent import decisions as decision_log
    from agent import discovery
    from agent.library import load as load_library
    from agent.ideas.service import (
        ANALYSIS_FAILED,
        CRITIQUE_FAILED,
        IDEA_CONFLICT,
        IDEA_NOT_FOUND,
        LINK_CONFLICT,
        LINK_NOT_FOUND,
        IdeaConflict,
        IdeaNotFound,
        IdeaService,
        IdeaUnavailable,
    )
    from agent.ideas.models import IDEA_DOMAINS, IDEA_POSITIONS
    from agent.trackers.habits import HabitTracker
    from agent.trackers.reflections import ReflectionService
    from agent.preferences import UserPreferencesService
    from agent.importing.service import ImportError_, ImportService
    from agent.work_queue import worker as queue_worker
    from agent import migrations

    COMPANION_AVAILABLE = True
    logger.info("PersonalAICompanion and db imported successfully")
except ImportError as e:
    COMPANION_AVAILABLE = False
    logger.error(f"ImportError: Could not import core components: {e}")
except Exception as e:
    COMPANION_AVAILABLE = False
    logger.error(f"Error importing PersonalAICompanion: {e}")

# Built single-page app (Vite output), served by this same process in production.
# In dev the Vite server on :5173 proxies /api here instead, so this stays unused.
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")

# Matches the archive extractor's own budget, so an upload that could never be
# unpacked is refused before it is written to disk rather than after.
MAX_IMPORT_UPLOAD_BYTES = 2 * 1024**3

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start up, or refuse to.

    Both failures below used to be logged and then ignored. A migration that
    did not apply left the process serving against a schema it did not expect,
    and starting the worker on top of it; a companion that failed to import
    left every data route to raise NameError on its first request while the
    health check reported the process up. The CLI already refused to start on a
    failed migration. The HTTP door now matches it: fail closed, loudly, before
    anything is served.
    """
    if not COMPANION_AVAILABLE:
        raise RuntimeError("IRIS core components failed to import; refusing to start "
                           "(see the ImportError logged above).")
    logger.info("Applying schema migrations...")
    migrations.upgrade()


    # Load the single pairing row after migrations, before accepting requests.
    # A failed load must not accidentally retain a previous in-process token.
    from agent.config import settings as live_settings
    live_settings.MOBILE_BEARER_HASH = None
    live_settings.LAN_BIND_ENABLED = False
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT bearer_hash, lan_bind_enabled FROM mobile_pairing WHERE id = 1"
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("mobile pairing row is missing")
        live_settings.MOBILE_BEARER_HASH = row[0]
        live_settings.LAN_BIND_ENABLED = bool(row[1])

    queue_worker.start()
    try:
        yield
    finally:
        queue_worker.stop()

# Initialize FastAPI app
app = FastAPI(title="IRIS Companion API", version="0.1.0", lifespan=lifespan)

# Keep the accidental non-loopback HTTP bind closed, too. The TLS listener
# additionally tags all its requests, including those from local processes.
from agent.mobile_auth import MobileAuthMiddleware, hash_token  # noqa: E402
app.add_middleware(MobileAuthMiddleware)

# A note on `def` versus `async def` below.
#
# Almost everything these handlers do is blocking: psycopg2 queries, embedding
# calls, the analytical engines, and in the review endpoint an LLM request.
# Declared `async def`, that work runs *on the event loop* and stalls every
# other request for its duration — including the SSE chat stream. Declared
# `def`, FastAPI runs the handler in a threadpool, which is the correct home
# for blocking work.
#
# So handlers are `def` unless they genuinely await something. The four that do
# — the health probe, the greeting, the proactive comment and the chat stream —
# stay `async def` and push their blocking parts through run_in_threadpool.

# ============================================================================
# DATA MODELS
# ============================================================================


# ============================================================================
# HABIT MODELS
# ============================================================================

class HabitCreate(BaseModel):
    """Create a new habit"""
    name: str
    description: str | None = None
    frequency_type: str = "daily"  # daily, weekly, specific_days
    habit_type: str = "completion"  # completion, duration, count
    weekly_target: float = 0
    tracking_metric: str | None = "completion"
    category: str | None = "general"

class HabitUpdate(BaseModel):
    """Update habit fields"""
    name: str | None = None
    description: str | None = None
    habit_type: str | None = None
    weekly_target: float | None = None
    tracking_metric: str | None = None
    is_active: bool | None = None

class HabitCompletion(BaseModel):
    """Log a habit completion"""
    habit_id: int
    value: float = 1.0
    date: str | None = None  # ISO date string, defaults to today
    notes: str | None = None

class HabitSkip(BaseModel):
    """Log a habit skip"""
    habit_id: int
    date: str | None = None  # ISO date string, defaults to today
    reason: str | None = None

class HabitResponse(BaseModel):
    """Habit response model"""
    id: int
    name: str
    description: str | None
    frequency_type: str
    category: str
    is_active: bool
    current_streak: int
    longest_streak: int
    total_completions: int
    created_at: str


# ============================================================================
# REFLECTION MODELS
# ============================================================================

class ReflectionCreate(BaseModel):
    """Create a new reflection"""
    content: str
    energy_level: int | None = None  # 1-10
    clarity_level: int | None = None # 1-10
    tags: list[str] | None = None
    reflection_date: str | None = None  # ISO date string

class ReflectionUpdate(BaseModel):
    """Update reflection fields"""
    content: str | None = None
    energy_level: int | None = None
    clarity_level: int | None = None
    tags: list[str] | None = None

class ReflectionResponse(BaseModel):
    """Reflection response model"""
    id: int
    reflection_date: str
    content: str
    mood: str | None
    energy_level: int | None
    clarity_level: int | None
    tags: list[str] | None
    created_at: str
    updated_at: str


# ============================================================================
# DECISION MODELS
# ============================================================================

class DecisionCreate(BaseModel):
    """A decision, as it is made. Only `what` is required: a journal that
    demands every answer at the moment of deciding gets skipped, and a skipped
    entry is worse for comparison than a partial one."""
    what: str = Field(min_length=1, max_length=500)
    decidedOn: date | None = None
    stake: Literal["little", "fair", "a_lot", "beyond_means"] | None = None
    reversible: Literal["easily", "at_a_cost", "not_at_all"] | None = None
    confidence: int | None = Field(default=None, ge=0, le=100)
    lastDays: Literal["setback", "success", "neither"] | None = None
    pressures: list[Literal["deadline", "money", "people", "urge"]] = Field(default_factory=list)
    sleepHours: float | None = Field(default=None, ge=0, le=24)
    energy: int | None = Field(default=None, ge=1, le=10)
    feeling: Literal["calm", "excited", "anxious", "frustrated"] | None = None
    plan: str | None = Field(default=None, max_length=1000)

class DecisionOutcome(BaseModel):
    """How it went, whether the plan was kept, and whether the owner would
    decide the same again: a different question from whether it went well."""
    outcome: str = Field(min_length=1, max_length=2000)
    followedPlan: Literal["yes", "partly", "no"] | None = None
    wouldRepeat: Literal["yes", "no", "unsure"] | None = None


# ============================================================================
# PATTERN MODELS
# ============================================================================

class OccasionVerdict(BaseModel):
    """Whether an occasion is really an instance of the pattern. None clears it."""
    verdict: Literal["yes", "no", "unsure"] | None = None
    note: str | None = Field(default=None, max_length=1000)

class PatternVerdict(BaseModel):
    """Whether the pattern rings true at all."""
    verdict: Literal["rings_true", "does_not", "unsure"]
    note: str | None = Field(default=None, max_length=1000)


# ============================================================================
# SINGLE-USER SEAM
# ============================================================================
# IRIS runs as a personal, single-user local app: one process, one database,
# bound to loopback. There is no login and no token — every route resolves (or
# lazily creates on first run) the one local user through get_current_user_id.
# Tests override this dependency via app.dependency_overrides.

DEFAULT_USERNAME = os.getenv("IRIS_DEFAULT_USER", "local")


def get_current_user_id() -> int:
    """Resolve the single local user's id, creating the user on first run."""
    return db.local_user_id(DEFAULT_USERNAME)


# ============================================================================
# ROOT & STATIC ENDPOINTS
# ============================================================================

# Mount the built SPA's static assets (Vite emits /assets/*).
if os.path.isdir(os.path.join(FRONTEND_DIST, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

# The page names the current build's hashed assets, so a browser that keeps an
# old copy keeps running the old app after an update. Revalidate it every time;
# the assets themselves are content-hashed and may be cached freely.
_SPA_HEADERS = {"Cache-Control": "no-cache"}


@app.get("/")
def root():
    """Serve the built SPA. Run `npm run build` in frontend/ if this 404s."""
    spa_index = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(spa_index):
        return FileResponse(spa_index, headers=_SPA_HEADERS)
    return {"message": "IRIS API online. SPA not built — run `npm run build` in frontend/."}

# Health check
@app.get("/health")
async def health_check():
    """Liveness *and* readiness: an API that cannot reach PostgreSQL is not
    healthy, and reporting ok regardless meant every data route returned 500
    while monitoring saw a green service."""
    checks = {"database": "down"}
    try:
        await run_in_threadpool(db.ping)
        checks["database"] = "ok"
    except Exception as e:
        logger.error(f"Health check: database unreachable: {e}")

    healthy = checks["database"] == "ok"
    return Response(
        content=json.dumps({
            "status": "ok" if healthy else "degraded",
            "checks": checks,
            "timestamp": datetime.now(UTC).isoformat(),
        }),
        media_type="application/json",
        status_code=200 if healthy else 503,
    )


# ============================================================================
# CHAT ENDPOINTS
# ============================================================================


# ============================================================================
# MOBILE ENDPOINTS (LAN-bind only, ADR-0018)
# ============================================================================

def _record_phone_contact(intake: bool) -> None:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE mobile_pairing SET last_seen_at = now(), "
            "last_intake_at = CASE WHEN %s THEN now() ELSE last_intake_at END WHERE id = 1",
            (intake,),
        )
        conn.commit()


@app.get("/api/mobile/connection")
def mobile_connection() -> dict:
    """Show the owner the phone listener, pairing and delivery health."""
    from agent.config import settings as live_settings
    from agent.mobile_auth import last_rejection

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT paired_at, last_seen_at, last_intake_at "
            "FROM mobile_pairing WHERE id = 1"
        )
        paired_at, last_seen_at, last_intake_at = cur.fetchone()
        cur.execute("SELECT count(*) FROM sensor_batches WHERE status = 'pending'")
        pending_batches = cur.fetchone()[0]
    listener = (
        "listening" if live_settings.LAN_URL else
        "failed" if live_settings.LAN_LISTENER_ERROR else
        "not_started" if live_settings.LAN_BIND_HOST else "not_configured"
    )
    return {
        "lan_url": live_settings.LAN_URL,
        "public_key_sha256": live_settings.LAN_PUBLIC_KEY_SHA256,
        "listener": listener,
        "listener_error": live_settings.LAN_LISTENER_ERROR,
        "paired": bool(live_settings.MOBILE_BEARER_HASH),
        "paired_at": paired_at,
        "last_seen_at": last_seen_at,
        "last_intake_at": last_intake_at,
        "last_rejection": last_rejection(),
        "pending_batches": pending_batches,
    }


@app.get("/api/mobile/status")
def mobile_status() -> dict:
    _record_phone_contact(False)
    return {"status": "connected"}


def _require_local_browser_origin(request: Request) -> None:
    # Browsers can send a cross-site simple POST to loopback without CORS.
    # A missing Origin is reserved for native local callers; browsers always
    # supply one on these mutations.
    origin = request.headers.get("origin")
    if origin is not None:
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
            "localhost", "127.0.0.1", "::1",
        }:
            raise HTTPException(status_code=403, detail="local browser origin required")


@app.post("/api/mobile/pair")
async def mobile_pair(request: Request) -> dict:
    """Store the SHA-256 of the 256-bit secret entered in local Settings."""
    _require_local_browser_origin(request)
    try:
        body = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid pairing request") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="invalid pairing request")
    token = body.get("token")
    if not isinstance(token, str) or re.fullmatch(r"[0-9a-fA-F]{64}", token) is None:
        raise HTTPException(status_code=400, detail="token must be 64 hexadecimal characters")
    enabled = body.get("lan_bind_enabled", True)
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=400, detail="lan_bind_enabled must be a boolean")
    bearer_hash = hash_token(token)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE mobile_pairing SET bearer_hash = %s, "
            "lan_bind_enabled = %s, paired_at = now(), "
            "paired_device = 'android', last_seen_at = NULL, "
            "last_intake_at = NULL WHERE id = 1",
            (bearer_hash, enabled))
        conn.commit()
    from agent.config import settings as live_settings
    live_settings.MOBILE_BEARER_HASH = bearer_hash
    live_settings.LAN_BIND_ENABLED = enabled
    from agent.mobile_auth import forget_rejection
    forget_rejection()
    return {"status": "paired", "lan_bind_enabled": enabled}


@app.post("/api/mobile/unpair")
def mobile_unpair(request: Request) -> dict:
    """Revoke the current bearer immediately, without closing the local UI."""
    _require_local_browser_origin(request)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE mobile_pairing SET bearer_hash = NULL, "
            "lan_bind_enabled = false, paired_at = NULL, "
            "paired_device = NULL, last_seen_at = NULL, "
            "last_intake_at = NULL WHERE id = 1"
        )
        conn.commit()
    from agent.config import settings as live_settings
    live_settings.MOBILE_BEARER_HASH = None
    live_settings.LAN_BIND_ENABLED = False
    from agent.mobile_auth import forget_rejection
    forget_rejection()
    return {"status": "unpaired"}


def _parse_sensor_payload(payload: object) -> dict:
    """Parse a live Pixel or Health Connect payload for owner review."""
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="sensor payload must be a JSON object")
    device = payload.get("device")
    if not isinstance(device, str) or not device.strip():
        raise HTTPException(status_code=400, detail="device required")
    from agent.sensors.adapters import REGISTRY

    if device.startswith("Pixel"):
        source = "pixel"
    elif device == "Health Connect" or device.lower().startswith("fitbit"):
        # Old queued phone deliveries retain their original bytes across retries.
        source = "health_connect"
    else:
        raise HTTPException(status_code=400, detail=f"unknown device {device!r}")
    try:
        return REGISTRY[source]().parse_from_dict(payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="invalid sensor payload") from exc

# A reviewed batch is stored as parsed JSONB; cap intake before decoding so
# an unbounded sensor payload cannot occupy memory or a single database row.
MAX_SENSOR_PAYLOAD_BYTES = 16 * 1024**2


def _decode_sensor_json(raw: bytes | bytearray) -> object:
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="invalid JSON sensor payload") from exc



def _clock_skew_seconds(sent_at: str | None) -> int | None:
    if not sent_at:
        return None
    try:
        sent = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if sent.tzinfo is None:
        return None
    return round((datetime.now(UTC) - sent).total_seconds())


@app.post("/api/mobile/sensor/intake")
async def mobile_sensor_intake(request: Request) -> dict:
    """Stage a phone batch for owner review; intake never admits evidence."""
    _require_local_browser_origin(request)
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_SENSOR_PAYLOAD_BYTES:
            raise HTTPException(status_code=413, detail="sensor payload exceeds 16 MB")
        raw.extend(chunk)
    batch = _parse_sensor_payload(_decode_sensor_json(raw))
    delivery_key = hashlib.sha256(raw).hexdigest()
    from agent.sensors.service import SensorService

    batch_id = await run_in_threadpool(
        SensorService().stage_delivery, batch,
        delivery_key=delivery_key,
        review_day=datetime.now(UTC).astimezone().date(),
        clock_skew_seconds=_clock_skew_seconds(request.headers.get("x-iris-sent-at")),
    )
    await run_in_threadpool(_record_phone_contact, True)
    from agent.sensors.repository import SensorRepository
    staged = await run_in_threadpool(SensorRepository().get_batch, batch_id)
    return {"batch_id": batch_id,
            "observation_count": staged["observation_count"],
            "dropped_count": staged["dropped_count"]}


# ============================================================================
# SENSOR REVIEW
# ============================================================================

class SensorBatchConfirm(BaseModel):
    links: dict[str, int | None]
    observation_count: int = Field(ge=0)

@app.get("/api/sensors/batches")
def list_sensor_batches(user_id: int = Depends(get_current_user_id)):
    """List staged sensor batches."""
    from agent.sensors.repository import SensorRepository
    return SensorRepository().list_batches()

@app.get("/api/sensors/batches/{batch_id}")
def get_sensor_batch(batch_id: int, user_id: int = Depends(get_current_user_id)):
    from agent.sensors.repository import SensorRepository
    batch = SensorRepository().get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch

@app.post("/api/sensors/batches/{batch_id}/confirm")
def confirm_sensor_batch(batch_id: int, payload: SensorBatchConfirm,
                         user_id: int = Depends(get_current_user_id)):
    from agent.sensors.service import SensorService
    from agent.sensors.repository import SensorBatchChanged, SensorRepository

    repo = SensorRepository()
    if repo.get_batch(batch_id) is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    try:
        SensorService().commit_batch(
            batch_id, links=payload.links, user_id=user_id,
            expected_observation_count=payload.observation_count,
        )
    except SensorBatchChanged as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return repo.get_batch(batch_id)


@app.post("/api/sensors/batches/{batch_id}/reject")
def reject_sensor_batch(batch_id: int, user_id: int = Depends(get_current_user_id)):
    from agent.sensors.repository import SensorRepository

    repo = SensorRepository()
    if repo.get_batch(batch_id) is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    try:
        repo.reject_batch(batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return repo.get_batch(batch_id)


@app.delete("/api/sensors/batches/{batch_id}")
def delete_sensor_batch(batch_id: int, user_id: int = Depends(get_current_user_id)):
    from agent.sensors.repository import SensorRepository

    repo = SensorRepository()
    if repo.get_batch(batch_id) is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    repo.delete_batch(batch_id)
    return {"status": "deleted"}


@app.post("/api/chat/greeting")
async def get_greeting(user_id: int = Depends(get_current_user_id)):
    """Get a dynamic greeting for the user."""
    try:
        companion = PersonalAICompanion(user_id=user_id)
        greeting = await run_in_threadpool(companion.generate_initial_greeting)
        return {"greeting": greeting}
    except Exception as e:
        logger.error(f"Greeting error: {e}")
        return {"greeting": "Hi, I'm Iris. How are you today?"}


@app.post("/api/chat/proactive")
async def proactive_chat(request: dict, user_id: int = Depends(get_current_user_id)):
    """Trigger a proactive comment from IRIS."""
    action_type = request.get("action_type")
    details = request.get("details", {})

    if not action_type:
        raise HTTPException(status_code=400, detail="action_type required")

    try:
        companion = PersonalAICompanion(user_id=user_id)
        iris_response = await run_in_threadpool(
            companion.generate_proactive_comment, action_type, details
        )
        # Response already persisted by companion.generate_proactive_comment() -> memory.add_message()
        return {"message": iris_response}
    except Exception as e:
        logger.error(f"Proactive error: {e}")
        return {"message": "..."} # Fail silently


# ============================================================================
# CONVERSATION ENDPOINTS (single-user; used by the integrated frontend)
# ============================================================================

def _iso(ts) -> str:
    return ts.isoformat() if hasattr(ts, "isoformat") else str(ts)



def _conversation_payload(user_id: int, session_id: str, started_at, last_at, count: int) -> dict:
    return {
        "id": session_id,
        "userId": str(user_id),
        "startedAt": _iso(started_at),
        "lastMessageAt": _iso(last_at or started_at),
        "messageCount": count,
    }


def _conversation_for(user_id: int, session: dict) -> dict:
    counts = db.chat_session_counts(user_id, session["id"])
    return _conversation_payload(
        user_id, session["id"], session["created_at"],
        counts["last_at"], counts["message_count"],
    )


@app.post("/api/conversations")
def start_conversation(user_id: int = Depends(get_current_user_id)):
    """Open an empty chat. Earlier messages stay stored and are not shown."""
    session = db.create_chat_session(user_id)
    now = session["created_at"]
    return _conversation_payload(user_id, session["id"], now, now, 0)


@app.get("/api/conversations/current")
def get_current_conversation(user_id: int = Depends(get_current_user_id)):
    """The latest open. Chat screens start a new one instead of calling this."""
    session = db.latest_chat_session(user_id) or db.create_chat_session(user_id)
    return _conversation_for(user_id, session)


@app.get("/api/conversations/{conversation_id}/messages")
def get_conversation_messages(conversation_id: str, user_id: int = Depends(get_current_user_id)):
    """Messages in this open only. An unknown open is empty, not another session."""
    if db.get_chat_session(user_id, conversation_id) is None:
        return []
    history = db.get_chat_history(user_id, limit=200, session_id=conversation_id)
    return [
        {
            "id": f"{conversation_id}_{i}",
            "conversationId": conversation_id,
            "role": "iris" if m["role"] == "assistant" else m["role"],
            "text": m["content"],
            "createdAt": _iso(m["created_at"]),
        }
        for i, m in enumerate(history)
    ]


@app.post("/api/conversations/{conversation_id}/messages/stream")
async def stream_conversation_reply(
    conversation_id: str,
    request: dict,
    user_id: int = Depends(get_current_user_id),
):
    """
    Stream IRIS's reply as Server-Sent Events, as the model writes it.

    This used to run the whole reply to completion and then drip it word by
    word, so the owner waited for the model and then again for an animation of
    a reply that already existed. Tokens are forwarded as they arrive now.

    Events: `{"text": ...}` per fragment, then `{"done": true, "messageId": ...}`.
    A failure is `{"error": ..., "saved": ...}` and is never rendered as
    something IRIS said: it used to arrive as a reply reading "I encountered an
    error…".

    `saved` is the owner's message, and it is the answer to one question: is
    what they typed now in the database? It is sent as `true` only after that
    write returns. It used to be `true` for every failure — including a failure
    of that write — and the browser, which discards the draft on that word,
    could lose the only copy of what they had written.
    """
    if db.get_chat_session(user_id, conversation_id) is None:
        raise HTTPException(status_code=404, detail="No such conversation.")
    text = (request or {}).get("text", "")

    async def event_gen():
        companion = PersonalAICompanion(user_id=user_id, session_id=conversation_id)
        try:
            turn = await run_in_threadpool(companion.begin_turn, text)
        except Exception as e:
            logger.error(f"Could not store the message that starts the turn: {e}")
            yield f"data: {json.dumps({'error': str(e), 'saved': False})}\n\n"
            return
        try:
            async for fragment in iterate_in_threadpool(companion.stream_reply(*turn)):
                yield f"data: {json.dumps({'text': fragment})}\n\n"
        except Exception as e:
            logger.error(f"Error streaming chat reply: {e}")
            yield f"data: {json.dumps({'error': str(e), 'saved': True})}\n\n"
            return
        message_id = f"{conversation_id}_{int(datetime.now(UTC).timestamp() * 1000)}"
        yield f"data: {json.dumps({'done': True, 'messageId': message_id})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


# ============================================================================
# HABIT ENDPOINTS
# ============================================================================

class AppHabitCreate(BaseModel):
    """Habit create payload from the integrated frontend (Pick<Habit,'name'|'tag'|'intent'|'color'>)."""
    name: str
    tag: str | None = None
    intent: str | None = None
    color: str | None = None


class HabitToggle(BaseModel):
    """Toggle a habit's completion for a date (defaults to today)."""
    done: bool
    date: str | None = None  # ISO date string


# Stable theme colors assigned deterministically when a habit has none stored.
HABIT_COLORS = ["sage", "amber", "indigo", "rose"]


def _habit_to_contract(habit: dict, user_id: int, window_days: int = 60) -> dict:
    """Map a habit DB row → the frontend `Habit` shape, incl. recentDays history."""
    hid = habit["id"]
    today = date.today()
    start = today - timedelta(days=window_days - 1)
    by_date = {c["completion_date"]: c for c in db.get_habit_completions(hid, start, today)}
    recent_days = []
    for i in range(window_days):
        c = by_date.get(start + timedelta(days=i))
        recent_days.append(1 if (c and c["is_completed"]) else 0)
    done_today = bool(by_date.get(today) and by_date[today]["is_completed"])
    return {
        "id": str(hid),
        "userId": str(user_id),
        "name": habit["name"],
        "tag": habit.get("category") or habit.get("frequency_type") or "daily",
        "intent": habit.get("description"),
        "color": habit.get("color") or HABIT_COLORS[hid % len(HABIT_COLORS)],
        "streakDays": habit.get("current_streak") or 0,
        "bestStreak": habit.get("longest_streak") or 0,
        "doneToday": done_today,
        "recentDays": recent_days,
    }


@app.get("/api/habits")
def list_habits(user_id: int = Depends(get_current_user_id)):
    """List all active habits (raw tracker shape; /api/habits/today is the UI contract)."""
    tracker = HabitTracker(user_id)
    habits = tracker.get_habits(active_only=True)
    return {"habits": habits}

@app.post("/api/habits")
def create_habit_app(habit: AppHabitCreate, user_id: int = Depends(get_current_user_id)):
    """Create a habit and return it in the frontend `Habit` contract shape."""
    tracker = HabitTracker(user_id)
    habit_id = tracker.create_habit(
        name=habit.name,
        description=habit.intent,
        category=habit.tag or "general",
    )
    contract = _habit_to_contract(tracker.get_habit(habit_id), user_id)
    if habit.color:
        contract["color"] = habit.color
    return contract

@app.get("/api/habits/today")
def get_today_habits(user_id: int = Depends(get_current_user_id)):
    """Today's habits + aggregates as the frontend `HabitsTodayResponse` shape."""
    tracker = HabitTracker(user_id)
    raw_habits = tracker.get_habits(active_only=True)
    habits = [_habit_to_contract(h, user_id) for h in raw_habits]
    # Divide by the habit's life so far, not a flat 30 days. A habit created
    # and kept today is 100% consistent, not 3% — which is both what the user
    # means and what /api/habits/consistency already answers. The two endpoints
    # used to give different answers to the same question.
    rates = []
    for row, contract in zip(raw_habits, habits, strict=True):
        age_days = _age_days(row.get("created_at")) + 1
        window = max(1, min(30, age_days))
        rates.append(sum(contract["recentDays"][-window:]) / window)
    return {
        "habits": habits,
        "doneCount": sum(1 for h in habits if h["doneToday"]),
        "totalCount": len(habits),
        "consistency30d": round(sum(rates) / len(rates), 3) if rates else 0.0,
        "longestActiveStreak": max((h["streakDays"] for h in habits), default=0),
    }

@app.post("/api/habits/{habit_id}/toggle")
def toggle_habit(habit_id: int, toggle: HabitToggle, user_id: int = Depends(get_current_user_id)):
    """Mark a habit done/undone for a date and return the updated `Habit`."""
    tracker = HabitTracker(user_id)
    if not tracker.get_habit(habit_id):
        raise HTTPException(status_code=404, detail="Habit not found")
    toggle_date = None
    if toggle.date:
        try:
            toggle_date = datetime.fromisoformat(toggle.date).date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format (use ISO format)")
    if toggle.done:
        tracker.log_completion(habit_id, toggle_date)
    else:
        db.uncomplete_habit(habit_id, toggle_date)
    tracker.update_streaks(habit_id)
    return _habit_to_contract(tracker.get_habit(habit_id), user_id)

@app.get("/api/habits/weekly")
def get_weekly_summary(user_id: int = Depends(get_current_user_id)):
    """Get weekly habit summary"""
    tracker = HabitTracker(user_id)
    summary = tracker.get_weekly_summary()
    return summary

@app.get("/api/habits/consistency/{days}")
def get_consistency_report(days: int = 30, user_id: int = Depends(get_current_user_id)):
    """Get consistency report across all habits"""

    tracker = HabitTracker(user_id)
    report = tracker.get_consistency_report(days)
    return report

@app.get("/api/habits/{habit_id}")
def get_habit(habit_id: int, user_id: int = Depends(get_current_user_id)):
    """Get details of a specific habit"""
    tracker = HabitTracker(user_id)
    habit = tracker.get_habit(habit_id)
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")
    return habit

@app.put("/api/habits/{habit_id}")
def update_habit(habit_id: int, updates: HabitUpdate, user_id: int = Depends(get_current_user_id)):
    """Update a habit's properties"""
    tracker = HabitTracker(user_id)
    if not tracker.get_habit(habit_id):
        raise HTTPException(status_code=404, detail="Habit not found")

    update_dict = updates.model_dump(exclude_none=True)
    tracker.update_habit(habit_id, **update_dict)
    return {"message": "Habit updated successfully"}

@app.delete("/api/habits/{habit_id}")
def delete_habit(habit_id: int, user_id: int = Depends(get_current_user_id)):
    """Delete a habit (soft-delete)"""
    tracker = HabitTracker(user_id)
    if not tracker.get_habit(habit_id):
        raise HTTPException(status_code=404, detail="Habit not found")

    tracker.delete_habit(habit_id)
    return {"message": "Habit deleted successfully"}

@app.post("/api/habits/complete")
def log_completion(completion: HabitCompletion, user_id: int = Depends(get_current_user_id)):
    """Log a habit completion"""
    tracker = HabitTracker(user_id)

    if not tracker.get_habit(completion.habit_id):
        raise HTTPException(status_code=404, detail="Habit not found")

    # Parse date if provided
    completion_date = None
    if completion.date:
        try:
            completion_date = datetime.fromisoformat(completion.date).date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format (use ISO format)")

    tracker.log_completion(completion.habit_id, completion_date, completion.value, completion.notes)
    streak_info = tracker.update_streaks(completion.habit_id)

    return {
        "message": "Completion logged successfully",
        "streaks": streak_info
    }

@app.post("/api/habits/skip")
def log_skip(skip: HabitSkip, user_id: int = Depends(get_current_user_id)):
    """Log a habit skip"""
    tracker = HabitTracker(user_id)

    if not tracker.get_habit(skip.habit_id):
        raise HTTPException(status_code=404, detail="Habit not found")

    # Parse date if provided
    skip_date = None
    if skip.date:
        try:
            skip_date = datetime.fromisoformat(skip.date).date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format (use ISO format)")

    tracker.log_skip(skip.habit_id, skip_date, skip.reason)
    return {"message": "Skip logged successfully"}

@app.get("/api/habits/{habit_id}/calendar")
def get_habit_calendar(habit_id: int, start: str, end: str, user_id: int = Depends(get_current_user_id)):
    """Get a calendar view of habit completions in a date range"""
    tracker = HabitTracker(user_id)

    if not tracker.get_habit(habit_id):
        raise HTTPException(status_code=404, detail="Habit not found")

    # Parse dates
    try:
        start_date = datetime.fromisoformat(start).date()
        end_date = datetime.fromisoformat(end).date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format (use ISO format)")

    calendar = tracker.get_calendar(habit_id, start_date, end_date)
    return {"calendar": calendar, "habit_id": habit_id}


# ============================================================================
# REFLECTION ENDPOINTS
# ============================================================================

@app.get("/api/reflections")
def list_reflections(user_id: int = Depends(get_current_user_id), limit: int = 30):
    """List recent reflections"""
    service = ReflectionService(user_id)
    reflections = service.get_reflections(limit=limit)
    return {"reflections": reflections}

@app.post("/api/reflections")
def create_reflection(reflection: ReflectionCreate, user_id: int = Depends(get_current_user_id)):
    """Create a new reflection"""
    service = ReflectionService(user_id)

    # Parse date if provided
    reflection_date = None
    if reflection.reflection_date:
        try:
            reflection_date = datetime.fromisoformat(reflection.reflection_date).date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format (use ISO format)")

    try:
        reflection_id = service.create_reflection(
            content=reflection.content,
            reflection_date=reflection_date,
            energy_level=reflection.energy_level,
            clarity_level=reflection.clarity_level,
            tags=reflection.tags
        )
        # No background task here: ReflectionService.create_reflection already
        # runs the pipeline. Scheduling it again embedded every reflection twice,
        # paying OpenAI twice and re-entering the window that made concurrent
        # ingests mis-attribute each other's content.
        return {"reflection_id": reflection_id, "message": "Reflection saved successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/reflections/moods")
def get_mood_trend(user_id: int = Depends(get_current_user_id), days: int = 30):
    """Get mood trend data"""
    service = ReflectionService(user_id)
    trend = service.get_mood_trend(days)
    return trend

@app.get("/api/reflections/summary")
def get_reflection_summary(user_id: int = Depends(get_current_user_id), days: int = 30):
    """Get comprehensive reflection summary"""
    service = ReflectionService(user_id)
    summary = service.get_reflection_summary(days)
    return summary

@app.get("/api/reflections/tags")
def get_tags_summary(user_id: int = Depends(get_current_user_id), days: int = 30):
    """Get tags summary from reflections"""
    service = ReflectionService(user_id)
    tags = service.get_tag_summary(days)
    return tags

@app.get("/api/reflections/{reflection_id}")
def get_reflection(reflection_id: int, user_id: int = Depends(get_current_user_id)):
    """Get a specific reflection"""
    service = ReflectionService(user_id)
    reflection = service.get_reflection(reflection_id)

    if not reflection:
        raise HTTPException(status_code=404, detail="Reflection not found")

    return reflection

@app.put("/api/reflections/{reflection_id}")
def update_reflection(reflection_id: int, updates: ReflectionUpdate, user_id: int = Depends(get_current_user_id)):
    """Update a reflection"""
    service = ReflectionService(user_id)

    if not service.get_reflection(reflection_id):
        raise HTTPException(status_code=404, detail="Reflection not found")

    try:
        update_dict = updates.model_dump(exclude_none=True)
        service.update_reflection(reflection_id, **update_dict)
        return {"message": "Reflection updated successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/reflections/{reflection_id}")
def delete_reflection(reflection_id: int, user_id: int = Depends(get_current_user_id)):
    """Delete a reflection"""
    service = ReflectionService(user_id)

    if not service.get_reflection(reflection_id):
        raise HTTPException(status_code=404, detail="Reflection not found")

    service.delete_reflection(reflection_id)
    return {"message": "Reflection deleted successfully"}


# ============================================================================
# JOURNAL ENDPOINTS (single-user; frontend JournalEntry mapped onto reflections)
# ============================================================================

class JournalCreate(BaseModel):
    """Journal create payload from the frontend (Pick<JournalEntry,'lines'|'energy'>)."""
    lines: list[str]
    # Named for what it is. This field used to be called "mood" while carrying
    # energy_level, so the weekly review reported average energy as "mood" while
    # reflections.mood — a categorical value inferred from tags — went unsent.
    energy: int | None = None  # 1-10, stored as the reflection's energy_level


def _reflection_to_journal(r: dict, user_id: int) -> dict:
    """Map a reflection row → the frontend `JournalEntry` shape.

    An entry whose day is unknown says so. `reflection_date or created_at`
    filled the gap with the minute the entry was imported, which is a date the
    owner never wrote and every reader downstream then treated as one
    (ADR-0013): the transcripts read as though they were written the afternoon
    the archive was opened.
    """
    content = r.get("content") or ""
    occurred = r.get("reflection_date")
    return {
        "id": str(r["id"]),
        "userId": str(user_id),
        "lines": content.split("\n"),
        "energy": r.get("energy_level"),
        "tags": r.get("tags") or [],
        # When it was written. `createdAt` preferred created_at, which for an
        # imported entry is the day it was imported, so a journal spanning two
        # years displayed as one afternoon in September.
        "occurredOn": occurred.isoformat() if hasattr(occurred, "isoformat") else None,
        "importedAt": _iso(r.get("created_at")),
        "createdAt": _iso(occurred) if occurred is not None else None,
        # Present only for entries that came from a recording, so the journal
        # can offer the audio next to the words it produced.
        "audioUrl": f"/api/audio/{r['id']}" if r.get("audio_path") else None,
    }


@app.get("/api/journal")
def list_journal(user_id: int = Depends(get_current_user_id),
                       limit: int = 50, cursor: str | None = None):
    """Return reflections as the frontend `JournalListResponse` (newest first).

    `cursor` is "<day>:<id>", or "undated:<id>" once paging reaches the entries
    whose day is unknown; `nextCursor` is returned only when another page
    exists. The frontend has always sent this parameter — it was previously
    ignored, so paging silently returned page one forever.

    Undated entries sort after every dated one (`db.get_journal_page`), so a
    page can end on one. This used to build the next cursor by calling
    `.isoformat()` on that row's absent date, which raised — on this archive,
    page three of the owner's own journal answered 500 and nothing older could
    be reached.
    """
    before = None
    if cursor:
        try:
            day, last_id = cursor.rsplit(":", 1)
            before = (None if day == "undated" else date.fromisoformat(day), int(last_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid cursor")

    # Ordered by the day each entry was written, so an imported archive reads as
    # a history. The cursor carries (date, id) because dates repeat.
    rows = db.get_journal_page(user_id, limit=limit + 1, before=before)
    has_more = len(rows) > limit
    rows = rows[:limit]

    body = {
        "entries": [_reflection_to_journal(r, user_id) for r in rows],
        "recurringPhrases": [],
    }
    if has_more and rows:
        last_day = rows[-1]["reflection_date"]
        day = last_day.isoformat() if last_day is not None else "undated"
        body["nextCursor"] = f"{day}:{rows[-1]['id']}"
    return body


@app.post("/api/journal")
def create_journal_entry(entry: JournalCreate, user_id: int = Depends(get_current_user_id)):
    """Create a reflection from journal lines/mood and return the `JournalEntry`."""
    service = ReflectionService(user_id)
    content = "\n".join(entry.lines).strip()
    if not content:
        raise HTTPException(status_code=400, detail="Journal entry cannot be empty")
    try:
        reflection_id = service.create_reflection(
            content=content,
            energy_level=entry.energy,
            tags=[],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _reflection_to_journal(service.get_reflection(reflection_id), user_id)


# ============================================================================
# DECISION ENDPOINTS (a decision journal; see agent/decisions.py)
# ============================================================================

def _decision_to_contract(row: dict) -> dict:
    """A stored decision in the frontend `Decision` shape."""
    return {
        "id": str(row["id"]),
        "decidedOn": row["decided_on"].isoformat(),
        "what": row["what"],
        "stake": row["stake"],
        "reversible": row["reversible"],
        "confidence": row["confidence"],
        "lastDays": row["last_days"],
        "pressures": list(row["pressures"] or []),
        "sleepHours": float(row["sleep_hours"]) if row["sleep_hours"] is not None else None,
        "energy": row["energy"],
        "feeling": row["feeling"],
        "plan": row["plan"],
        "outcome": row["outcome"],
        "followedPlan": row["followed_plan"],
        "wouldRepeat": row["would_repeat"],
        "closedAt": row["closed_at"].isoformat() if row["closed_at"] else None,
    }


@app.get("/api/decisions")
def list_decisions(user_id: int = Depends(get_current_user_id)):
    """Every recorded decision, newest first."""
    return {"decisions": [_decision_to_contract(r) for r in decision_log.list_for(user_id)]}


@app.post("/api/decisions")
def create_decision(body: DecisionCreate, user_id: int = Depends(get_current_user_id)):
    """Record a decision as it is made."""
    if not body.what.strip():
        raise HTTPException(status_code=422, detail="Say what the decision is.")
    row = decision_log.create(
        user_id, what=body.what, decided_on=body.decidedOn, stake=body.stake,
        reversible=body.reversible, confidence=body.confidence, last_days=body.lastDays,
        pressures=list(body.pressures), sleep_hours=body.sleepHours, energy=body.energy,
        feeling=body.feeling, plan=body.plan)
    return _decision_to_contract(row)


@app.patch("/api/decisions/{decision_id}")
def record_decision_outcome(decision_id: int, body: DecisionOutcome,
                            user_id: int = Depends(get_current_user_id)):
    """How it went, the plan, and whether the same again. Recording it again corrects it."""
    if not body.outcome.strip():
        raise HTTPException(status_code=422, detail="Say what happened.")
    row = decision_log.record_outcome(user_id, decision_id, outcome=body.outcome,
                                      followed_plan=body.followedPlan,
                                      would_repeat=body.wouldRepeat)
    if row is None:
        raise HTTPException(status_code=404, detail="No such decision.")
    return _decision_to_contract(row)


# ============================================================================
# PATTERN ENDPOINTS (discovery; see agent/discovery.py and patterns/library.json)
# ============================================================================

def _library() -> dict:
    return {p.id: p for p in load_library()}


def _pattern_contract(p) -> dict:
    return {"id": p.id, "name": p.name, "statement": p.statement,
            "holdsWhen": list(p.holds_when), "notWhen": list(p.not_when),
            "question": p.question, "basis": p.basis or None,
            "evidence": p.evidence or None, "source": p.source or None}


@app.get("/api/patterns")
def list_patterns(user_id: int = Depends(get_current_user_id)):
    """Every library pattern, with its occasions counted by how they went."""
    return {"patterns": [
        {**_pattern_contract(s["pattern"]), "occasions": s["occasions"], "tones": s["tones"],
         "reviewed": s["reviewed"], "rejected": s["rejected"], "labelledBy": s["labelledBy"],
         "verdict": s["verdict"]}
        for s in discovery.summaries(user_id, list(_library().values()))]}


@app.get("/api/patterns/{pattern_id}")
def get_pattern(pattern_id: str, user_id: int = Depends(get_current_user_id)):
    """One pattern: its occasions on both sides, and what else was true on each."""
    library = _library()
    if pattern_id not in library:
        raise HTTPException(status_code=404, detail="No such pattern.")
    d = discovery.detail(user_id, library[pattern_id])
    return {
        "pattern": _pattern_contract(d["pattern"]),
        "occasions": [{
            "id": str(o["id"]),
            "occurredOn": o["occurred_on"].isoformat() if o["occurred_on"] else None,
            "domain": o["domain"], "situation": o["situation"], "response": o["response"],
            "outcome": o["outcome"], "explanation": o["explanation"],
            "citations": [{"entryId": str(c.get("entryId")), "sourceType": c.get("sourceType", "reflection"),
                           "entryDate": c.get("entryDate"), "text": c.get("text")}
                          for c in (o["citations"] or [])],
            "tone": o["label"]["tone"], "size": o["label"]["size"],
            "labelledBy": o["label"]["labelled_by"],
            "ownerVerdict": o["label"]["owner_verdict"], "verdictNote": o["label"]["verdict_note"],
        } for o in d["occasions"]],
        "alsoTrue": d["alsoTrue"],
        "distinctive": [{"patternId": pid, "name": library[pid].name if pid in library else pid,
                         "better": better, "worse": worse} for pid, better, worse in d["distinctive"]],
        "verdict": d["verdict"],
    }


@app.put("/api/patterns/{pattern_id}/occasions/{occasion_id}")
def put_occasion_verdict(pattern_id: str, occasion_id: int, body: OccasionVerdict,
                         user_id: int = Depends(get_current_user_id)):
    """Whether this occasion is really an instance of the pattern."""
    if not discovery.set_occasion_verdict(user_id, pattern_id, occasion_id, body.verdict, body.note):
        raise HTTPException(status_code=404, detail="That occasion is not labelled with this pattern.")
    return {"ok": True}


@app.get("/api/differences")
def list_differences(user_id: int = Depends(get_current_user_id)):
    """Insights: differences in outcome between a pattern's better and worse occasions."""
    return {"differences": discovery.differences(user_id, list(_library().values()))}


@app.put("/api/differences/{pattern_id}/{other_pattern_id}/verdict")
def put_difference_verdict(pattern_id: str, other_pattern_id: str, body: PatternVerdict,
                           user_id: int = Depends(get_current_user_id)):
    """Whether a difference in outcome rings true."""
    library = _library()
    if pattern_id not in library or other_pattern_id not in library or pattern_id == other_pattern_id:
        raise HTTPException(status_code=404, detail="No such difference.")
    discovery.set_difference_verdict(user_id, pattern_id, other_pattern_id, body.verdict, body.note)
    return {"ok": True}


@app.put("/api/patterns/{pattern_id}/verdict")
def put_pattern_verdict(pattern_id: str, body: PatternVerdict,
                        user_id: int = Depends(get_current_user_id)):
    """Whether the pattern rings true at all."""
    if pattern_id not in _library():
        raise HTTPException(status_code=404, detail="No such pattern.")
    discovery.set_pattern_verdict(user_id, pattern_id, body.verdict, body.note)
    return {"ok": True}


# ============================================================================
# SETTINGS ENDPOINTS (single-user; User/UserPreferences, knowledge)
# ============================================================================

# Incoming PATCH /user/preferences keys (frontend camelCase) → app_settings columns.
_PREF_KEY_MAP = {
    "tone": "tone",
    "density": "density",
    "dailyCheckinTime": "daily_checkin_time",
    "weeklyReviewTime": "weekly_review_time",
    "maxNudgesPerDay": "max_nudges_per_day",
    "threadsListenedFor": "threads",
}

def _age_days(ts) -> int:
    """Whole days between a timestamp (datetime or ISO string) and now."""
    if not ts:
        return 0
    try:
        dt = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
    except (ValueError, TypeError):
        return 0
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return max(0, (datetime.now() - dt).days)


def _user_to_contract(user_id: int) -> dict:
    """Build the frontend `User` shape from users + user_app_settings."""
    s = db.get_app_settings(user_id) or {}
    created = s.get("created_at")
    return {
        "id": str(user_id),
        "name": s.get("name") or "",
        "createdAt": _iso(created) if created else _iso(datetime.now(UTC)),
        "dayInJourney": _age_days(created) if created else 0,
        "timezone": s.get("timezone") or "UTC",
        "preferences": {
            "tone": s.get("tone") or "warm",
            "density": s.get("density") or "balanced",
            "dailyCheckinTime": s.get("daily_checkin_time"),
            "weeklyReviewTime": s.get("weekly_review_time"),
            "maxNudgesPerDay": s.get("max_nudges_per_day") if s.get("max_nudges_per_day") is not None else 3,
            "threadsListenedFor": s.get("threads") or [],
        },
    }


@app.get("/api/user")
def get_app_user(user_id: int = Depends(get_current_user_id)):
    """Return the frontend `User` (profile + app preferences)."""
    return _user_to_contract(user_id)


@app.patch("/api/user/preferences")
def update_app_preferences(prefs: dict, user_id: int = Depends(get_current_user_id)):
    """Merge a Partial<UserPreferences> into the app-settings store; return `User`."""
    fields = {_PREF_KEY_MAP[k]: v for k, v in prefs.items() if k in _PREF_KEY_MAP}
    if fields:
        db.upsert_app_settings(user_id, **fields)
    return _user_to_contract(user_id)


# ============================================================================
# IMPORT ENDPOINTS (bringing existing writing in from other tools)
# ============================================================================


def _batch_to_contract(batch: dict) -> dict:
    counts = batch.get("counts") or {}
    return {
        "id": str(batch["id"]),
        "kind": batch["kind"],
        "adapter": batch.get("adapter"),
        "detected": batch.get("detected") or [],
        "originalFilename": batch.get("original_filename"),
        "status": batch["status"],
        "error": batch.get("error"),
        "entryCount": batch.get("entry_count") or 0,
        "committedCount": batch.get("committed_count") or 0,
        "createdAt": _iso(batch["created_at"]),
        "counts": {
            "total": counts.get("total", 0),
            "staged": counts.get("staged", 0),
            "excluded": counts.get("excluded", 0),
            "duplicate": counts.get("duplicate", 0),
            "imported": counts.get("imported", 0),
            "failed": counts.get("failed", 0),
            # The number that decides whether a commit is allowed at all.
            "needsDate": counts.get("needs_date", 0),
            # Recordings still being transcribed: nothing to commit yet, and
            # nothing the owner can fix except wait.
            "awaitingTranscript": counts.get("awaiting_transcript", 0),
            "earliest": counts["earliest"].isoformat() if counts.get("earliest") else None,
            "latest": counts["latest"].isoformat() if counts.get("latest") else None,
        },
    }


def _item_to_contract(item: dict) -> dict:
    return {
        "id": str(item["id"]),
        "sourceName": item.get("source_name"),
        "title": item.get("title"),
        # Enough to recognise the entry in a list without shipping the archive.
        "excerpt": (item.get("content") or "")[:280],
        "occurredOn": item["entry_date"].isoformat() if item.get("entry_date") else None,
        "dateSource": item.get("date_source"),
        "dateConfidence": item.get("date_confidence"),
        # Offered, never applied: the day the entry's file was last saved.
        "fileModifiedOn": (item["file_modified_at"].astimezone().date().isoformat()
                           if item.get("file_modified_at") else None),
        "status": item["status"],
        # The owner has looked and says the day is not recoverable — a
        # different state from "the parser found nothing", and the only one
        # that may be committed undated (ADR-0013).
        "dateUnknownAccepted": bool(item.get("date_unknown_accepted")),
        "warnings": item.get("warnings") or [],
        "hasAudio": bool(item.get("audio_path")),
        "error": item.get("error"),
    }


@app.post("/api/import/audio")
async def upload_import_audio(
    file: UploadFile = File(...),
    recordedAt: str | None = Form(None),
    capturedSource: str = Form("upload"),
    batchId: int | None = Form(None),
    user_id: int = Depends(get_current_user_id),
):
    """Take a voice journal, keep it, and queue it for transcription.

    Async because it awaits the upload; streamed to disk so a long recording is
    not held in memory. The recording is stored before anything else happens, so
    a transcription failure delays the transcript rather than losing the audio.
    """
    from agent.importing.audio import AUDIO_SUFFIXES, enqueue_transcription, stage_recording
    from agent.importing import store as import_store

    name = Path(file.filename or "recording.webm").name
    if Path(name).suffix.lower() not in AUDIO_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"{Path(name).suffix or 'That file'} is not an audio format IRIS can read.",
        )

    staging = Path(tempfile.mkdtemp(prefix="iris-audio-"))
    destination = staging / name
    size = 0
    try:
        with destination.open("wb") as out:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > MAX_IMPORT_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="That recording is too large.")
                out.write(chunk)

        def stage() -> dict:
            service = ImportService(user_id)
            # Resolved and authorised server-side; a supplied id is a claim.
            batch = service.batch_for_append(batchId, "audio", name)
            staged = stage_recording(user_id, batch, destination, name, recordedAt)
            enqueue_transcription(staged["item_id"], user_id)
            import_store.update_batch(
                batch, entry_count=import_store.counts(batch).get("total", 0)
            )
            return {"batchId": str(batch), **staged}

        staged = await run_in_threadpool(stage)
        return {
            "batchId": staged["batchId"],
            "entryId": str(staged["item_id"]),
            "durationSeconds": staged.get("duration_seconds"),
            "capturedSource": capturedSource,
            # The transcript arrives on the queue; the page polls for it.
            "transcriptionStatus": "pending",
        }
    except ImportError_ as e:
        # Without this, the authorisation check below surfaced as a 500.
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        shutil.rmtree(staging, ignore_errors=True)


@app.get("/api/audio/{reflection_id}")
def get_reflection_audio(reflection_id: int, user_id: int = Depends(get_current_user_id)):
    """Serve a kept recording. FileResponse handles Range, so playback seeks."""
    from agent.importing.audio import media_type_for, resolve

    reflection = db.get_reflection(reflection_id)
    if not reflection or reflection.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="No such entry.")
    if not reflection.get("audio_path"):
        raise HTTPException(status_code=404, detail="That entry has no recording.")
    try:
        path = resolve(reflection["audio_path"])
    except ValueError:
        # A stored path that escapes the audio root should never exist; if one
        # does, refusing to open it is the only safe answer.
        raise HTTPException(status_code=404, detail="That recording is unavailable.")
    if not path.exists():
        raise HTTPException(status_code=404, detail="That recording is unavailable.")
    return FileResponse(path, media_type=media_type_for(path))


@app.get("/api/import/adapters")
def list_import_adapters(user_id: int = Depends(get_current_user_id)):
    """The formats IRIS can read. Served from the registry so the UI cannot
    drift from what actually exists."""
    from agent.importing import REGISTRY

    return [{"name": a.name, "label": a.label, "description": a.description}
            for a in REGISTRY]


@app.post("/api/import/batches")
async def create_import_batch(
    file: UploadFile = File(...),
    adapter: str | None = Form(None),
    kind: str = Form("text"),
    lastModified: int | None = Form(None),
    user_id: int = Depends(get_current_user_id),
):
    """Accept an upload and stage what it contains for review.

    Async because it genuinely awaits the upload. Streamed to disk in chunks
    rather than `await file.read()`, which would hold an entire export in memory.
    Everything after the bytes land is blocking, so it goes to the threadpool.

    `lastModified` is the browser's reading of when the file was last saved, in
    milliseconds. The server's own copy cannot know it.
    """
    staging = Path(tempfile.mkdtemp(prefix="iris-upload-"))
    destination = staging / (Path(file.filename or "upload").name or "upload")
    size = 0
    try:
        with destination.open("wb") as out:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > MAX_IMPORT_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="That file is larger than the import limit (2 GB).",
                    )
                out.write(chunk)

        service = ImportService(user_id)
        batch = await run_in_threadpool(
            service.create_batch, destination, file.filename or "upload", kind, adapter,
            lastModified / 1000 if lastModified else None,
        )
        return _batch_to_contract(batch)
    except ImportError_ as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        shutil.rmtree(staging, ignore_errors=True)


@app.get("/api/import/batches")
def list_import_batches(user_id: int = Depends(get_current_user_id)):
    return [_batch_to_contract(b) for b in ImportService(user_id).list_batches()]


@app.get("/api/import/batches/{batch_id}")
def get_import_batch(batch_id: int, user_id: int = Depends(get_current_user_id)):
    try:
        return _batch_to_contract(ImportService(user_id).get_batch(batch_id))
    except ImportError_ as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/import/batches/{batch_id}/entries")
def list_import_entries(batch_id: int, status: str | None = None,
                        limit: int = 500, offset: int = 0,
                        user_id: int = Depends(get_current_user_id)):
    try:
        items = ImportService(user_id).list_items(batch_id, status, limit, offset)
    except ImportError_ as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"entries": [_item_to_contract(i) for i in items]}


class ImportEntryUpdate(BaseModel):
    """Corrections the owner makes during review."""
    occurredOn: str | None = None
    status: str | None = None
    content: str | None = None


@app.patch("/api/import/entries/{entry_id}")
def update_import_entry(entry_id: int, update: ImportEntryUpdate,
                        user_id: int = Depends(get_current_user_id)):
    occurred = None
    if update.occurredOn:
        try:
            occurred = date.fromisoformat(update.occurredOn)
        except ValueError:
            raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD.")
    try:
        item = ImportService(user_id).update_item(
            entry_id, entry_date=occurred, status=update.status, content=update.content
        )
    except ImportError_ as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _item_to_contract(item)


class ImportBulk(BaseModel):
    ids: list[int]
    op: str                       # 'exclude' | 'include' | 'set_date' | 'use_file_date'
    occurredOn: str | None = None


@app.post("/api/import/entries/bulk")
def bulk_update_import_entries(payload: ImportBulk,
                               user_id: int = Depends(get_current_user_id)):
    occurred = None
    if payload.occurredOn:
        try:
            occurred = date.fromisoformat(payload.occurredOn)
        except ValueError:
            raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD.")
    try:
        updated = ImportService(user_id).bulk(payload.ids, payload.op, occurred)
    except ImportError_ as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"updated": updated}


class ImportReparse(BaseModel):
    adapter: str


@app.post("/api/import/batches/{batch_id}/reparse")
def reparse_import_batch(batch_id: int, payload: ImportReparse,
                         user_id: int = Depends(get_current_user_id)):
    """Read the upload again as a different format. Detection is a guess; this
    is how it is overruled."""
    try:
        return _batch_to_contract(ImportService(user_id).reparse(batch_id, payload.adapter))
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Unknown format: {e}")
    except ImportError_ as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/import/batches/{batch_id}/commit")
def commit_import_batch(batch_id: int, user_id: int = Depends(get_current_user_id)):
    """Create the reflections. Refused while any included entry has no date."""
    try:
        return ImportService(user_id).commit(batch_id)
    except ImportError_ as e:
        # 409: the request is well formed, the batch is simply not ready.
        raise HTTPException(status_code=409, detail=str(e))


@app.delete("/api/import/batches/{batch_id}")
def delete_import_batch(batch_id: int, withReflections: bool = False,
                        user_id: int = Depends(get_current_user_id)):
    try:
        return ImportService(user_id).delete_batch(batch_id, withReflections)
    except ImportError_ as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# Analytical gates.
#
# CONTEXT.md: "User preferences override all gates". They always have, in the
# engines — the confidence threshold, the item budget and engine enablement are
# read from user_preferences on every analysis. What was missing was any way to
# set them outside the CLI, so the documented control existed for a user with a
# terminal and not for the one using the app.
#
# These are deliberately separate from /api/user/preferences, which is tone,
# density and nudges: those change how IRIS speaks, these change what it is
# willing to claim.
# ---------------------------------------------------------------------------

_ANALYSIS_KEY_MAP = {
    "minConfidence": "min_confidence",
    "maxItems": "max_items",
    "enabledEngines": "enabled_engines",
}

def _analysis_to_contract(prefs: dict) -> dict:
    return {
        "minConfidence": prefs.get("min_confidence", "medium"),
        "maxItems": prefs.get("max_items", 5),
        # null means "every engine", which is not the same as "none of them";
        # the UI needs to tell those apart to render the toggles.
        "enabledEngines": prefs.get("enabled_engines"),
        # The same set PATCH validates against. This used to be a second list,
        # frozen at the six engines of 2024: the owner could be shown a
        # two-year count and had no switch for it, and the observations engine
        # this set was widened for was still missing from the menu.
        "availableEngines": sorted(SELECTABLE_ENGINES),
    }


@app.get("/api/user/analysis")
def get_analysis_preferences(user_id: int = Depends(get_current_user_id)):
    """The gates that decide what IRIS is willing to say."""
    return _analysis_to_contract(UserPreferencesService(user_id).get_prefs())


@app.patch("/api/user/analysis")
def update_analysis_preferences(prefs: dict, user_id: int = Depends(get_current_user_id)):
    """Merge a partial set of gates. Rejects invalid values rather than
    silently ignoring them, so a control that appears to work does."""
    service = UserPreferencesService(user_id)
    unknown = set(prefs) - set(_ANALYSIS_KEY_MAP)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown setting(s): {', '.join(sorted(unknown))}",
        )

    for wire_key, value in prefs.items():
        try:
            service.update_pref(_ANALYSIS_KEY_MAP[wire_key], value)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return _analysis_to_contract(service.get_prefs())


@app.post("/api/user/analysis/reset")
def reset_analysis_preferences(user_id: int = Depends(get_current_user_id)):
    """Restore the defaults."""
    return _analysis_to_contract(UserPreferencesService(user_id).reset())


@app.get("/api/knowledge")
def list_knowledge(user_id: int = Depends(get_current_user_id)):
    """Return the user's themes as the frontend `KnownFact[]`."""
    return [
        {
            "id": str(t["id"]),
            "fact": t["summary"],
            # A pattern the owner confirmed is not the same kind of thing as a
            # cluster the machine found, and forgetting them does different
            # things — the screen has to be able to say which.
            "source": "confirmed" if t.get("origin") == "observed" else "pattern",
            "ageDays": _age_days(t.get("first_seen_at")),
            "editable": True,
        }
        for t in db.get_themes(user_id)
    ]


@app.delete("/api/knowledge/{fact_id}")
def forget_knowledge(fact_id: int, user_id: int = Depends(get_current_user_id)):
    """Forget a fact, guarding ownership.

    A cluster is derived — found by the machine, and found again by a rebuild —
    so forgetting one deletes it. A construct is the owner's record: a pattern
    they read the quotes for and confirmed. This route used to delete those too,
    one click labelled like trivia, cascading away the prototypes and the
    decision itself. Forgetting one now retracts it, exactly as the Noticed
    screen does: it stops being counted, its evidence goes, and the sentences
    it was built from and the fact that it was declined are kept, so a rerun of
    discovery cannot propose it again.
    """
    theme = db.get_theme_by_id(fact_id)
    if not theme or theme.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Fact not found")
    if theme.get("origin") == "observed":
        db.retract_construct(fact_id)
        return {"ok": True, "retracted": True}
    db.delete_theme(fact_id)
    return {"ok": True, "retracted": False}



# ============================================================================
# ONBOARDING ENDPOINTS (single-user; configures the local user)
# ============================================================================

def _onboarding_state(user_id: int) -> dict:
    """Whether first run has happened.

    There were five steps here — name, reason, threads, a body source and a
    review cadence — collected through an answer endpoint no screen called:
    the app's first run is one honest paragraph and one button. A step that
    asked for a wearable IRIS has said it will not connect was the museum
    piece.
    """
    s = db.get_app_settings(user_id) or {}
    return {"step": "done" if s.get("onboarding_completed") else "welcome"}


@app.get("/api/onboarding/state")
def get_onboarding_state(user_id: int = Depends(get_current_user_id)):
    """Return the current OnboardingState."""
    return _onboarding_state(user_id)


@app.post("/api/onboarding/complete")
def complete_onboarding(user_id: int = Depends(get_current_user_id)):
    """Mark onboarding complete and return the configured `User`."""
    db.upsert_app_settings(user_id, onboarding_completed=True)
    return _user_to_contract(user_id)


# ============================================================================
# INSIGHTS ENDPOINTS (single-user; engine outputs → InsightSummary/InsightDetail)
# ============================================================================

class InsightSnooze(BaseModel):
    """POST /insights/:id/snooze body."""
    days: int = 30


@app.get("/api/insights")
def list_insights(user_id: int = Depends(get_current_user_id)):
    """Return InsightSummary[] from the analytical engines (snoozed/resolved hidden)."""
    return InsightsService(user_id).list_summaries()


@app.get("/api/insights/coverage")
def get_insights_coverage(user_id: int = Depends(get_current_user_id)):
    """How much recent evidence there is to reason from.

    Declared before /api/insights/{insight_id} so "coverage" is not read as an
    insight id.
    """
    return InsightsService(user_id).coverage()


@app.get("/api/insights/{insight_id}")
def get_insight_detail(insight_id: str, user_id: int = Depends(get_current_user_id)):
    """Return the InsightDetail for one engine-derived insight."""
    detail = InsightsService(user_id).get_detail(insight_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Insight not found")
    db.mark_insight_seen(user_id, insight_id)
    return detail


class ObservationRequest(BaseModel):
    """What to read. Deliberately small: this is a button, not a configuration."""
    limit: int = OBSERVATION_MAX_ENTRIES_READ
    since: date | None = None


@app.post("/api/observations")
def read_entries(body: ObservationRequest, user_id: int = Depends(get_current_user_id)):
    """Read the owner's entries and report what recurs, with verbatim quotes.

    One of the two paths that send journal entries to the model for analysis;
    the other is discovery (/api/constructs/discover). Both are POSTs with no
    caller inside IRIS: they happen when the owner asks, and at no other time.
    This quick read stores nothing — what comes back is something IRIS noticed
    while reading, shown with its receipts. Discovery stores what it finds as
    proposals the owner reviews (ADR-0016).
    """
    engine = ObservationEngine(user_id)
    observations = apply_preferences(engine.read(limit=body.limit, since=body.since), user_id)
    return {
        "observations": [o.as_dict() for o in observations],
        "entriesRead": observations[0].entries_read if observations else 0,
    }


class DiscoverRequest(BaseModel):
    """Whether to include the staged recordings. Nothing else to configure."""
    includeStaged: bool = True


@app.get("/api/constructs")
def list_constructs(status: str = "candidate", user_id: int = Depends(get_current_user_id)):
    """Constructs awaiting a decision, each with the quotes it rests on."""
    if status != "candidate":
        raise HTTPException(status_code=400, detail="Only candidates are reviewable.")
    return {"constructs": constructs.candidates(user_id)}


@app.get("/api/constructs/last-run")
def last_discovery_run(user_id: int = Depends(get_current_user_id)):
    """What the last archive read found and what it let go, as counts.

    The support check fails closed, so a model that answers badly empties the
    review screen. Without these numbers that looked exactly like an archive
    with nothing to say. Counts only: no claim or quote leaves this route.
    """
    run = db.get_latest_observation_run(user_id)
    if run is None:
        return {"run": None}
    dropped = {k: int(v) for k, v in (run["dropped"] or {}).items()}
    return {"run": {
        "status": run["status"],
        "startedAt": _iso(run["started_at"]),
        "finishedAt": _iso(run["finished_at"]),
        "entriesRead": run["entries_read"],
        "passesPlanned": run["passes_planned"],
        "passesCompleted": run["passes_completed"],
        "rawFindings": run["raw_findings"],
        "staged": run["candidates_staged"],
        "dropped": {
            "mergedAway": dropped.get("merged_away", 0),
            "unchecked": dropped.get("unchecked", 0),
            "incomplete": dropped.get("incomplete", 0),
            "denied": dropped.get("denied", 0),
            "tooFewSupporting": dropped.get("too_few_supporting", 0),
            "alreadyDecided": dropped.get("already_decided", 0),
            "notEmbedded": dropped.get("not_embedded", 0),
        },
        # Runs before migration 0016 recorded no reasons at all.
        "dropsRecorded": bool(dropped),
    }}


@app.post("/api/constructs/discover")
def discover_constructs(body: DiscoverRequest, user_id: int = Depends(get_current_user_id)):
    """Read the whole archive and stage what was found, for review.

    Like /api/observations this sends journal entries to the model, and like it
    this has no caller inside IRIS: it happens when the owner asks. Unlike it,
    what comes back is kept — as candidates that no engine measures until they
    are confirmed.
    """
    return {"constructs": constructs.discover(user_id, include_staged=body.includeStaged)}


@app.post("/api/constructs/{theme_id}/confirm")
def confirm_construct(theme_id: int, user_id: int = Depends(get_current_user_id)):
    """Vouch for a construct, and measure it against the whole archive."""
    theme = db.get_theme_by_id(theme_id)
    if not theme or theme.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Construct not found")
    occurrences = constructs.confirm(theme_id)
    if occurrences < 0:
        # Already active, already rejected, or not a construct the reader
        # proposed. Reporting success would tell the owner their decision was
        # recorded when nothing changed.
        raise HTTPException(
            status_code=409,
            detail="This is no longer awaiting a decision. Reload the review list.")
    return {"id": str(theme_id), "status": "active", "occurrences": occurrences}


@app.post("/api/constructs/{theme_id}/reject")
def reject_construct(theme_id: int, user_id: int = Depends(get_current_user_id)):
    """Set a construct aside. It is kept, and never measured."""
    theme = db.get_theme_by_id(theme_id)
    if not theme or theme.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Construct not found")
    constructs.reject(theme_id)
    return {"id": str(theme_id), "status": "rejected"}


def _citation_ids(values: list[str]) -> list[int]:
    parsed: list[int] = []
    for raw in values:
        if not isinstance(raw, str) or not raw.isdecimal():
            raise HTTPException(status_code=422, detail="citation ids must be integers")
        parsed.append(int(raw))
    return parsed




def _require_enum(value: str | None, allowed: tuple[str, ...], name: str) -> None:
    if value is not None and value not in allowed:
        raise HTTPException(status_code=422, detail=f"invalid {name}")


def _idea_call(action):
    try:
        return action()
    except IdeaNotFound:
        raise HTTPException(status_code=404, detail=IDEA_NOT_FOUND)
    except IdeaConflict:
        raise HTTPException(status_code=409, detail=IDEA_CONFLICT)


def _analysis_result(result: dict) -> dict:
    if result["run"]["status"] == "failed":
        raise HTTPException(status_code=502, detail=ANALYSIS_FAILED)
    return result


class ConfirmIdeaBody(BaseModel):
    citationIds: list[str]
    position: str
    domain: str


class RejectCitationsBody(BaseModel):
    citationIds: list[str]


class UpdateIdeaBody(BaseModel):
    position: str | None = None
    domain: str | None = None


@app.get("/api/ideas/framework")
def get_ideas_framework(user_id: int = Depends(get_current_user_id)):
    """Active ideas, accepted links, and the derived graph. No model call."""
    return IdeaService(user_id).framework()


@app.get("/api/ideas/review")
def get_ideas_review(user_id: int = Depends(get_current_user_id)):
    """Proposals and new quotations waiting for a decision. No model call."""
    return IdeaService(user_id).review()


@app.post("/api/ideas/discover")
def discover_ideas(user_id: int = Depends(get_current_user_id)):
    """Read eligible reflections and stage idea proposals. Owner-triggered."""
    return _analysis_result(IdeaService(user_id).discover())


@app.post("/api/ideas/links/{link_id}/confirm")
def confirm_idea_link(link_id: int, user_id: int = Depends(get_current_user_id)):
    try:
        return IdeaService(user_id).confirm_link(link_id)
    except IdeaNotFound:
        raise HTTPException(status_code=404, detail=LINK_NOT_FOUND)
    except IdeaConflict:
        raise HTTPException(status_code=409, detail=LINK_CONFLICT)


@app.post("/api/ideas/links/{link_id}/reject")
def reject_idea_link(link_id: int, user_id: int = Depends(get_current_user_id)):
    try:
        return IdeaService(user_id).reject_link(link_id)
    except IdeaNotFound:
        raise HTTPException(status_code=404, detail=LINK_NOT_FOUND)
    except IdeaConflict:
        raise HTTPException(status_code=409, detail=LINK_CONFLICT)


@app.get("/api/ideas/{idea_id}")
def get_idea(idea_id: int, user_id: int = Depends(get_current_user_id)):
    return _idea_call(lambda: IdeaService(user_id).detail(idea_id))


@app.post("/api/ideas/{idea_id}/confirm")
def confirm_idea(idea_id: int, body: ConfirmIdeaBody, user_id: int = Depends(get_current_user_id)):
    _require_enum(body.position, IDEA_POSITIONS, "position")
    _require_enum(body.domain, IDEA_DOMAINS, "domain")
    citation_ids = _citation_ids(body.citationIds)
    return _idea_call(lambda: IdeaService(user_id).confirm(
        idea_id, citation_ids, body.position, body.domain))


@app.post("/api/ideas/{idea_id}/reject")
def reject_idea(idea_id: int, user_id: int = Depends(get_current_user_id)):
    return _idea_call(lambda: IdeaService(user_id).reject(idea_id))


@app.post("/api/ideas/{idea_id}/citations/reject")
def reject_idea_citations(
    idea_id: int, body: RejectCitationsBody, user_id: int = Depends(get_current_user_id),
):
    citation_ids = _citation_ids(body.citationIds)
    return _idea_call(lambda: IdeaService(user_id).reject_citations(idea_id, citation_ids))


@app.patch("/api/ideas/{idea_id}")
def update_idea(idea_id: int, body: UpdateIdeaBody, user_id: int = Depends(get_current_user_id)):
    if body.position is None and body.domain is None:
        raise HTTPException(status_code=422, detail="position or domain is required")
    _require_enum(body.position, IDEA_POSITIONS, "position")
    _require_enum(body.domain, IDEA_DOMAINS, "domain")
    return _idea_call(lambda: IdeaService(user_id).update(
        idea_id, position=body.position, domain=body.domain))


@app.post("/api/ideas/{idea_id}/links/discover")
def discover_idea_links(idea_id: int, user_id: int = Depends(get_current_user_id)):
    return _analysis_result(_idea_call(lambda: IdeaService(user_id).discover_links(idea_id)))


@app.post("/api/ideas/{idea_id}/critique")
def critique_idea(idea_id: int, user_id: int = Depends(get_current_user_id)):
    try:
        return IdeaService(user_id).critique(idea_id)
    except IdeaNotFound:
        raise HTTPException(status_code=404, detail=IDEA_NOT_FOUND)
    except IdeaConflict:
        raise HTTPException(status_code=409, detail=IDEA_CONFLICT)
    except IdeaUnavailable:
        raise HTTPException(status_code=502, detail=CRITIQUE_FAILED)


@app.post("/api/insights/{insight_id}/snooze")
def snooze_insight(insight_id: str, body: InsightSnooze, user_id: int = Depends(get_current_user_id)):
    """Snooze an insight for N days; returns the updated InsightSummary."""
    service = InsightsService(user_id)
    summary = service.get_summary(insight_id, force_status="snoozed")
    if summary is None:
        raise HTTPException(status_code=404, detail="Insight not found")
    db.set_insight_status(user_id, insight_id, "snoozed",
                          datetime.now(UTC) + timedelta(days=body.days))
    return summary


@app.post("/api/insights/{insight_id}/resolve")
def resolve_insight(insight_id: str, user_id: int = Depends(get_current_user_id)):
    """Resolve (dismiss) an insight; returns the updated InsightSummary."""
    service = InsightsService(user_id)
    summary = service.get_summary(insight_id, force_status="resolved")
    if summary is None:
        raise HTTPException(status_code=404, detail="Insight not found")
    db.set_insight_status(user_id, insight_id, "resolved")
    return summary


# ============================================================================
# REVIEW ENDPOINTS (single-user; weekly aggregation + LLM letter)
# ============================================================================

def _avg_energy(reflections) -> float | None:
    """Mean self-reported energy, or None when none was reported.

    0.0 used to stand in for "nothing reported", so a week with no energy scores
    read as the lowest week possible and the next one as a large rise.
    """
    energies = [r["energy_level"] for r in reflections if r.get("energy_level") is not None]
    return round(sum(energies) / len(energies), 1) if energies else None


#: A week's worth of entries, with room for an imported archive's heaviest week.
#: Beyond this the totals would be wrong rather than incomplete, so the letter
#: says so instead of quietly reporting a partial week as the whole one.
WEEK_ENTRY_LIMIT = 500


def _build_review_week(user_id: int, week_start: date) -> dict:
    """Assemble the frontend `ReviewWeek` from reflections, habits and findings.

    No scores. "Wins" were entries with energy of 7 or more, and each day got a
    word bucketed from its energy — IRIS scoring the owner's week in a product
    whose rule is that it does not. A day shows the energy the owner reported,
    or that nothing was written. Sleep/HRV are absent: there is no body data
    source, by design.
    """
    week_end = week_start + timedelta(days=6)
    service = ReflectionService(user_id)

    # Every entry in the interval, not the first page of them. get_reflections
    # defaults to 30, so a busy or freshly imported week reported the counts,
    # averages and "nothing written" days of whichever 30 came back.
    this_week = service.get_reflections(start_date=week_start, end_date=week_end,
                                        limit=WEEK_ENTRY_LIMIT)
    prev_week = service.get_reflections(
        start_date=week_start - timedelta(days=7),
        end_date=week_start - timedelta(days=1),
        limit=WEEK_ENTRY_LIMIT,
    )
    energy_avg = _avg_energy(this_week)
    previous = _avg_energy(prev_week)
    energy_delta = (round(energy_avg - previous, 1)
                    if energy_avg is not None and previous is not None else None)

    # The owner's own energy for each day, when they gave one.
    written_on, by_date = set(), {}
    for r in this_week:
        written_on.add(r["reflection_date"])
        if r.get("energy_level") is not None:
            by_date.setdefault(r["reflection_date"], r["energy_level"])
    days = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        energy = by_date.get(d)
        days.append({
            "date": d.isoformat(),
            "shortName": d.strftime("%a").lower(),
            "energy": energy,
            "word": (f"{energy}/10" if energy is not None
                     else "written" if d in written_on else "no entry"),
        })

    tracker = HabitTracker(user_id)
    habits = tracker.get_habits(active_only=True)
    habits_hit = 0
    for h in habits:
        comps = db.get_habit_completions(h["id"], week_start, week_end)
        if any(c.get("is_completed") for c in comps):
            habits_hit += 1

    themes_list = [t["summary"] for t in db.get_themes(user_id)[:3] if t.get("summary")]

    settings = db.get_app_settings(user_id) or {}
    lookahead = []
    if settings.get("weekly_review_time"):
        lookahead.append({"when": settings["weekly_review_time"], "what": "Weekly review"})
    if settings.get("daily_checkin_time"):
        lookahead.append({"when": f"Daily {settings['daily_checkin_time']}", "what": "Check-in"})

    # Findings are computed now, from everything written since. They belong to
    # a letter about this week only while "this week" is the current one; in a
    # letter about an old week they would be later observations presented as
    # what IRIS noticed then.
    is_current_week = week_end >= date.today()
    letter = _review_letter(user_id, this_week, written_on, energy_avg, energy_delta,
                            habits_hit, len(habits), with_findings=is_current_week)

    return {
        "weekStart": week_start.isoformat(),
        "weekEnd": week_end.isoformat(),
        "letter": letter,
        "metrics": {
            "energyAvg": energy_avg,
            "energyDelta": energy_delta,
            "habitsHit": habits_hit,
            "habitsTotal": len(habits),
        },
        "days": days,
        "themes": themes_list,
        "lookahead": lookahead,
    }


def _review_letter(user_id, this_week, written_on, energy_avg, energy_delta,
                   habits_hit, habits_total, with_findings: bool = True) -> str:
    """The week's letter, held to the rules (agent/review_letter.py).

    `with_findings` is False for a past week: what IRIS has noticed is computed
    from the whole record as it stands today, so putting it in a letter about
    March would read as something it noticed in March.
    """
    import agent.core as core_module
    from agent import review_letter
    from agent.narrative import NarrativeFormatter
    from agent.pipeline_orchestrator import admit
    from agent.prioritization import InsightPrioritizationEngine

    n = len(this_week)
    facts = [f"You wrote {n} entr{'y' if n == 1 else 'ies'} on {len(written_on)} of the 7 days."
             if n else "Nothing was written this week."]
    if energy_avg is not None:
        facts.append(f"The energy you reported averaged {energy_avg}"
                     + (f", {abs(energy_delta)} {'higher' if energy_delta > 0 else 'lower'} than the week before."
                        if energy_delta else "."))
    if habits_total:
        facts.append(f"You kept {habits_hit} of {habits_total} habits at least once.")

    findings: list[str] = []
    if with_findings:
        try:
            admission = admit(user_id)
            chosen = InsightPrioritizationEngine(user_id).select(admission.findings, 3)
            findings = NarrativeFormatter.format_all(chosen)
        except Exception as e:
            logger.warning(f"Findings unavailable for the letter: {e}")

    try:
        intelligence = core_module.Intelligence()
    except Exception as e:  # pragma: no cover - no API key
        logger.warning(f"No model for the letter: {e}")
        intelligence = None
    return review_letter.compose(facts, findings, [r["content"] for r in this_week], intelligence)


@app.get("/api/review/latest")
def get_latest_review(user_id: int = Depends(get_current_user_id)):
    """ReviewWeek for the most recent 7-day window ending today."""
    week_start = date.today() - timedelta(days=6)
    return _build_review_week(user_id, week_start)


@app.get("/api/review/week/{start}")
def get_review_week(start: str, user_id: int = Depends(get_current_user_id)):
    """ReviewWeek for the 7-day window beginning on the given ISO date."""
    try:
        week_start = date.fromisoformat(start)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date (use YYYY-MM-DD)")
    return _build_review_week(user_id, week_start)


# ============================================================================
# SPA FALLBACK (serve client-side routes from the built frontend)
# ============================================================================
# Registered last so it never shadows /api/*, /assets, or /health. Active only
# when the SPA is built (frontend/dist), so dev (Vite on :5173) is unaffected.
if os.path.exists(os.path.join(FRONTEND_DIST, "index.html")):

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        """Return index.html for unknown non-API paths so React Router can route."""
        if full_path.startswith(("api/", "assets/")) or full_path == "health":
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"), headers=_SPA_HEADERS)


# ============================================================================
# RUN THE APP (for local testing)
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
