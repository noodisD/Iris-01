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
from agent import observability as obs  # noqa: E402
from agent.observability import logs as obs_logs, runtime as obs_runtime  # noqa: E402
obs.setup("server")
logger = logging.getLogger("iris_api")

import asyncio
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
from fastapi import Depends, FastAPI, File, Form, HTTPException, Path as ApiPath, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from typing import Literal

from pydantic import BaseModel, Field
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool

# Load environment variables
load_dotenv()

# Import the companion system
try:
    from agent.constants import SELECTABLE_ENGINES
    from agent.core import PersonalAICompanion
    from agent.database import db
    from agent.insights_service import InsightsService
    from agent import constructs
    from agent import decisions as decision_log
    from agent import discovery
    from agent.library import load as load_library
    from agent.ideas.service import (
        ANALYSIS_FAILED,
        CRITIQUE_FAILED,
        IDEA_CONFLICT,
        IDEA_DUPLICATE,
        IDEA_NOT_FOUND,
        LINK_CONFLICT,
        LINK_NOT_FOUND,
        IdeaConflict,
        IdeaDuplicate,
        IdeaNotFound,
        IdeaService,
        IdeaUnavailable,
    )
    from agent.ideas.models import IDEA_DOMAINS, IDEA_POSITIONS, NOTES_LIMIT, STATEMENT_LIMIT
    from agent.trackers.habits import HabitTracker
    from agent.trackers.reflections import ReflectionService
    from agent.preferences import UserPreferencesService
    from agent.importing.service import ImportError_, ImportService
    from agent.work_queue import worker as queue_worker
    from agent import migrations
    from agent import voice

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
    obs_logs.attach("uvicorn", logging.INFO)
    with obs.span("system.startup", "system", entry=True, root=True) as current:
        obs.capture_input({"role": "server"}, span=current)
        logger.info("Applying schema migrations...")
        migrations.upgrade()

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
        obs.capture_output({"status": "initialized"}, span=current)
        _publish_table_catalog()
    obs_runtime.start_background(probe=True)
    loop_watch = asyncio.create_task(obs_runtime.watch_event_loop())
    queue_worker.start()
    try:
        yield
    finally:
        queue_worker.stop()
        loop_watch.cancel()
        obs_runtime.stop_background()

# Initialize FastAPI app
app = FastAPI(title="IRIS Companion API", version="0.1.0", lifespan=lifespan)

# Keep the accidental non-loopback HTTP bind closed, too. The TLS listener
# additionally tags all its requests, including those from local processes.
from agent.mobile_auth import MobileAuthMiddleware, hash_token  # noqa: E402
from agent.observability.http import TracingMiddleware  # noqa: E402
app.add_middleware(MobileAuthMiddleware)
app.add_middleware(TracingMiddleware)

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

# ============================================================================
# REFLECTION MODELS
# ============================================================================

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
    """The displayed account feedback, with an optional tone correction."""
    verdict: Literal["yes", "no", "unsure"] | None
    note: str | None = Field(default=None, max_length=1000)
    ownerTone: Literal["better", "worse", "mixed"] | None = None

class PatternVerdict(BaseModel):
    """The displayed pattern or comparison feedback, including note-only."""
    verdict: Literal["rings_true", "does_not", "unsure"] | None
    note: str | None = Field(default=None, max_length=1000)

class DiscoveryRefresh(BaseModel):
    scope: Literal["unread", "failed"]


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
    from agent.mobile_auth import connection_status

    with db.connection() as conn, conn.cursor() as cur:
        return connection_status(cur)


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

def _remote_sensor_review(request: Request) -> bool:
    return bool(request.scope.get("iris_lan") or request.scope.get("iris_tailnet"))


def _reviewable_batch(request: Request, batch: dict | None) -> dict:
    # Timeline coordinates arrive by laptop upload; the phone's own Pixel
    # batches remain reviewable, but imported locations stay on the laptop.
    if not batch or (batch["source"] == "google_timeline" and _remote_sensor_review(request)):
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@app.get("/api/sensors/batches")
def list_sensor_batches(request: Request, user_id: int = Depends(get_current_user_id)):
    """List staged sensor batches without exposing laptop Timeline imports remotely."""
    from agent.sensors.repository import SensorRepository
    batches = SensorRepository().list_batches()
    if _remote_sensor_review(request):
        return [batch for batch in batches if batch["source"] != "google_timeline"]
    return batches

@app.get("/api/sensors/batches/{batch_id}")
def get_sensor_batch(batch_id: int, request: Request, user_id: int = Depends(get_current_user_id)):
    from agent.sensors.repository import SensorRepository
    return _reviewable_batch(request, SensorRepository().get_batch(batch_id))

@app.post("/api/sensors/batches/{batch_id}/confirm")
def confirm_sensor_batch(batch_id: int, payload: SensorBatchConfirm, request: Request,
                         user_id: int = Depends(get_current_user_id)):
    from agent.sensors.service import SensorService
    from agent.sensors.repository import SensorBatchChanged, SensorRepository

    repo = SensorRepository()
    _reviewable_batch(request, repo.get_batch(batch_id))
    try:
        SensorService().commit_batch(
            batch_id, links=payload.links, user_id=user_id,
            expected_observation_count=payload.observation_count,
        )
        from agent.days.recompute import batch_days, recompute
        days = batch_days(user_id, batch_id)
        if days:
            recompute(user_id, days)
    except SensorBatchChanged as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return repo.get_batch(batch_id)


@app.post("/api/sensors/batches/{batch_id}/reject")
def reject_sensor_batch(batch_id: int, request: Request, user_id: int = Depends(get_current_user_id)):
    from agent.sensors.repository import SensorRepository

    repo = SensorRepository()
    _reviewable_batch(request, repo.get_batch(batch_id))
    try:
        # Only a pending batch can be rejected, and pending readings never
        # reach a day, so there is nothing to recompute.
        repo.reject_batch(batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return repo.get_batch(batch_id)


@app.delete("/api/sensors/batches/{batch_id}")
def delete_sensor_batch(batch_id: int, request: Request, user_id: int = Depends(get_current_user_id)):
    from agent.sensors.repository import SensorRepository

    repo = SensorRepository()
    _reviewable_batch(request, repo.get_batch(batch_id))
    from agent.days.recompute import batch_days, recompute
    days = batch_days(user_id, batch_id)  # before the readings go with the batch
    repo.delete_batch(batch_id)
    if days:
        recompute(user_id, days)
    return {"status": "deleted"}


MAX_TIMELINE_UPLOAD_BYTES = 80 * 1024 ** 2


class ConfirmRange(BaseModel):
    start: date
    end: date
    links: dict[str, int | None] = Field(default_factory=dict)


class PlaceBody(BaseModel):
    name: str
    kind: Literal["home", "office", "other"]
    lat: float
    lon: float
    radiusM: int = 150
    source: Literal["owner", "timeline"] = "owner"


class CategoryBody(BaseModel):
    package: str
    category: str


def _no_coordinates(value: object) -> None:
    banned = {"lat", "lon", "latitude", "longitude", "coordinates"}
    if isinstance(value, dict):
        if banned & set(value):
            raise HTTPException(status_code=500, detail="day features must not include coordinates")
        for item in value.values():
            _no_coordinates(item)
    elif isinstance(value, list):
        for item in value:
            _no_coordinates(item)


@app.post("/api/sensors/import/google-timeline")
async def import_google_timeline(file: UploadFile, user_id: int = Depends(get_current_user_id)):
    """Stage a Timeline export. Coordinates stay in the sensor tables."""
    raw = await file.read(MAX_TIMELINE_UPLOAD_BYTES + 1)
    if len(raw) > MAX_TIMELINE_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="timeline export is too large")
    from agent.sensors.timeline import stage_export
    try:
        return await run_in_threadpool(stage_export, raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/sensors/confirm-range")
def confirm_sensor_range(body: ConfirmRange, user_id: int = Depends(get_current_user_id)):
    """Confirm every pending Timeline batch in the range, one commit_batch each."""
    from agent.days.recompute import batch_days, recompute
    from agent.sensors.repository import SensorBatchChanged, SensorRepository
    from agent.sensors.service import SensorService
    if body.end < body.start:
        raise HTTPException(status_code=400, detail="range is backwards")
    repo = SensorRepository()
    service = SensorService()
    confirmed: list[int] = []
    touched: set = set()
    try:
        for batch in repo.pending_between("google_timeline", body.start, body.end):
            try:
                service.commit_batch(
                    batch["id"], links=body.links, user_id=user_id,
                    expected_observation_count=batch["observation_count"],
                )
            except SensorBatchChanged as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            confirmed.append(batch["id"])
            touched.update(batch_days(user_id, batch["id"]))
    finally:
        # Batches confirmed before a failure stay confirmed, so their days
        # are rebuilt either way rather than left stale.
        if touched:
            recompute(user_id, sorted(touched))
    return {"confirmed": confirmed}


@app.get("/api/places")
def list_places(user_id: int = Depends(get_current_user_id)):
    from agent.days.places import list_places as _list
    return {"places": _list(user_id)}


@app.get("/api/places/suggestions")
def suggest_places(user_id: int = Depends(get_current_user_id)):
    from agent.days.places import suggest_from_timeline
    return suggest_from_timeline(user_id)


@app.post("/api/places")
def create_place(body: PlaceBody, user_id: int = Depends(get_current_user_id)):
    from agent.days.places import create_place as _create
    from agent.days.recompute import recompute
    try:
        place = _create(user_id, name=body.name, kind=body.kind, lat=body.lat, lon=body.lon,
                        radius_m=body.radiusM, source=body.source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    recompute(user_id)
    return place


@app.patch("/api/places/{place_id}")
def update_place(place_id: int, body: PlaceBody, user_id: int = Depends(get_current_user_id)):
    from agent.days.places import update_place as _update
    from agent.days.recompute import recompute
    try:
        place = _update(user_id, place_id, name=body.name, kind=body.kind, lat=body.lat,
                        lon=body.lon, radius_m=body.radiusM)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if place is None:
        raise HTTPException(status_code=404, detail="place not found")
    recompute(user_id)
    return place


@app.delete("/api/places/{place_id}")
def delete_place(place_id: int, user_id: int = Depends(get_current_user_id)):
    from agent.days.places import remove_place
    from agent.days.recompute import recompute
    if not remove_place(user_id, place_id):
        raise HTTPException(status_code=404, detail="place not found")
    recompute(user_id)
    return {"status": "deleted"}


@app.get("/api/app-categories")
def list_app_categories(user_id: int = Depends(get_current_user_id)):
    from agent.days.places import list_categories
    return {"categories": list_categories(user_id)}


@app.put("/api/app-categories")
def put_app_category(body: CategoryBody, user_id: int = Depends(get_current_user_id)):
    from agent.days.places import set_category
    from agent.days.recompute import recompute
    if not body.package.strip() or not body.category.strip():
        raise HTTPException(status_code=400, detail="package and category are required")
    set_category(user_id, body.package, body.category)
    recompute(user_id)
    return {"package": body.package.strip(), "category": body.category.strip()}


@app.get("/api/days")
def list_day_features(user_id: int = Depends(get_current_user_id)):
    from agent.days.recompute import list_days
    body = {"days": list_days(user_id)}
    _no_coordinates(body)
    return body


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
    # A turn that will be heard, not read (ADR-0025): same storage and context,
    # one instruction more.
    spoken = bool((request or {}).get("voice"))
    evidence_ref = (request or {}).get("evidenceRef")


    async def event_gen():
        # Constructed inside the try: with no API key configured it raises, and
        # after the stream has begun an uncaught error only drops the connection
        # instead of sending the error event the client knows how to show.
        from agent.evidence_ref import EvidenceChanged, EvidenceNotCurrent, EvidenceNotFound
        try:
            if evidence_ref is not None and (spoken or not isinstance(evidence_ref, dict)):
                yield f"data: {json.dumps({'error': 'Selected evidence is for typed discussion only.', 'saved': False})}\n\n"
                return
            companion = PersonalAICompanion(user_id=user_id, session_id=conversation_id)
            if evidence_ref is None:
                turn = await run_in_threadpool(companion.begin_turn, text, spoken)
            else:
                turn = await run_in_threadpool(companion.begin_turn, text, spoken,
                                               evidence_ref=evidence_ref)
        except EvidenceChanged as e:
            yield f"data: {json.dumps({'error': str(e), 'saved': False})}\n\n"
            return
        except (EvidenceNotCurrent, EvidenceNotFound, ValueError) as e:
            if evidence_ref is None:
                logger.error("Could not start the turn: %s", e)
                yield f"data: {json.dumps({'error': str(e), 'saved': False})}\n\n"
            else:
                logger.info("Selected evidence lookup failed: %s", type(e).__name__)
                yield f"data: {json.dumps({'error': 'Selected evidence is unavailable. Review it before sending.', 'saved': False})}\n\n"
            return
        except Exception as e:
            logger.error(f"Could not start the turn: {e}")
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
# TALKING WITH IRIS (ADR-0025): speech in and out around an ordinary chat turn
# ============================================================================

class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=voice.MAX_SPEECH_CHARS)


@app.get("/api/voice/estimate")
def voice_estimate(user_id: int = Depends(get_current_user_id)):
    """What one spoken turn would cost. Sends nothing."""
    return voice.estimate(user_id)


@app.post("/api/voice/transcribe")
async def voice_transcribe(audio: UploadFile = File(...), user_id: int = Depends(get_current_user_id)):
    """What the owner said, as text. The audio is not kept."""
    data = await audio.read(voice.MAX_UTTERANCE_BYTES + 1)
    try:
        text = await run_in_threadpool(voice.transcribe_utterance, data, audio.content_type or "")
    except voice.TooLong as e:
        raise HTTPException(status_code=413, detail=str(e)) from e
    except voice.VoiceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Transcription of a spoken turn failed: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail="IRIS could not hear that. Try again.") from e
    return {"text": text}


@app.post("/api/voice/speech")
async def voice_speech(body: SpeechRequest, user_id: int = Depends(get_current_user_id)):
    """IRIS's words as speech (MP3), streamed as they are made."""
    try:
        chunks = await run_in_threadpool(voice.open_speech, body.text)
    except voice.VoiceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:  # no API key
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.error("Speech could not be made: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail="IRIS could not speak that.") from e
    return StreamingResponse(iterate_in_threadpool(chunks), media_type="audio/mpeg")


# ============================================================================
# HABIT ENDPOINTS
# ============================================================================

class AppHabitCreate(BaseModel):
    """Habit create payload from the integrated frontend (Pick<Habit,'name'|'tag'|'intent'>).

    No colour: habits have no colour column, so one sent here appeared once and
    was gone on the next load. A habit's colour follows from its id.
    """
    name: str
    tag: str | None = None
    intent: str | None = None


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
        "color": HABIT_COLORS[hid % len(HABIT_COLORS)],
        "streakDays": habit.get("current_streak") or 0,
        "bestStreak": habit.get("longest_streak") or 0,
        "doneToday": done_today,
        "recentDays": recent_days,
    }


@app.post("/api/habits")
def create_habit_app(habit: AppHabitCreate, user_id: int = Depends(get_current_user_id)):
    """Create a habit and return it in the frontend `Habit` contract shape."""
    tracker = HabitTracker(user_id)
    habit_id = tracker.create_habit(
        name=habit.name,
        description=habit.intent,
        category=habit.tag or "general",
    )
    return _habit_to_contract(tracker.get_habit(habit_id), user_id)

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

# ============================================================================
# REFLECTION ENDPOINTS
# ============================================================================

# ============================================================================
# JOURNAL ENDPOINTS (single-user; frontend JournalEntry mapped onto reflections)
# ============================================================================

class Checkin(BaseModel):
    """Optional 1–10 self-report. Energy is stored on the reflection, not in metrics."""
    energy: int | None = Field(default=None, ge=1, le=10)
    mood: int | None = Field(default=None, ge=1, le=10)
    sleep_quality: int | None = Field(default=None, ge=1, le=10)
    stress: int | None = Field(default=None, ge=1, le=10)
    focus: int | None = Field(default=None, ge=1, le=10)


class JournalCreate(BaseModel):
    """Journal create payload.

    Older phone builds send `lines` and `energy`. Current clients send `text`,
    `format` and `checkin`. A check-in with no text is allowed.
    """
    lines: list[str] | None = None
    # Named for what it is. This field used to be called "mood" while carrying
    # energy_level, so the weekly review reported average energy as "mood" while
    # reflections.mood — a categorical value inferred from tags — went unsent.
    energy: int | None = Field(default=None, ge=1, le=10)
    text: str | None = None
    format: Literal["plain", "markdown"] | None = None
    checkin: Checkin | None = None


_CHECKIN_METRICS = ("mood", "sleep_quality", "stress", "focus")


def _metric_value(metrics: object, key: str) -> int | None:
    if not isinstance(metrics, dict):
        return None
    item = metrics.get(key)
    if isinstance(item, dict) and item.get("source") == "checkin":
        value = item.get("value")
        return value if isinstance(value, int) else None
    return None


def _checkin_from_row(r: dict) -> dict:
    metrics = r.get("metrics")
    return {
        "energy": r.get("energy_level"),
        "mood": _metric_value(metrics, "mood"),
        "sleep_quality": _metric_value(metrics, "sleep_quality"),
        "stress": _metric_value(metrics, "stress"),
        "focus": _metric_value(metrics, "focus"),
    }


def _checkin_metrics(checkin: Checkin) -> dict | None:
    metrics = {
        key: {"value": getattr(checkin, key), "scale": 10, "source": "checkin"}
        for key in _CHECKIN_METRICS
        if getattr(checkin, key) is not None
    }
    return metrics or None


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
        "text": content,
        "format": r.get("content_format") or "plain",
        "energy": r.get("energy_level"),
        "checkin": _checkin_from_row(r),
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
    """Create a reflection from journal text or the older lines payload."""
    service = ReflectionService(user_id)
    if entry.text is not None:
        content = entry.text.strip()
        content_format = entry.format or "markdown"
    else:
        content = "\n".join(entry.lines or []).strip()
        content_format = entry.format or "plain"
    energy = entry.energy
    metrics = None
    if entry.checkin is not None:
        if entry.checkin.energy is not None:
            energy = entry.checkin.energy
        metrics = _checkin_metrics(entry.checkin)
    if not content and energy is None and not metrics:
        raise HTTPException(status_code=400, detail="Journal entry cannot be empty")
    try:
        reflection_id = service.create_reflection(
            content=content,
            energy_level=energy,
            tags=[],
            metrics=metrics,
            content_format=content_format,
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

def _occasion_contract(o: dict) -> dict:
    label = o["label"]
    return {
        "id": str(o["id"]),
        "recordedOn": o["occurred_on"].isoformat() if o["occurred_on"] else None,
        "domain": o["domain"], "situation": o["situation"], "response": o["response"],
        "outcome": o["outcome"], "explanation": o["explanation"],
        "citations": [{"entryId": str(c["entryId"]), "sourceType": c["sourceType"],
                       "entryDate": c.get("entryDate"), "text": c["text"]}
                      for c in (o["citations"] or [])],
        "tone": label["tone"], "suggestedTone": label["suggested_tone"],
        "ownerTone": label["owner_tone"], "size": label["size"],
        "labelledBy": label["labelled_by"], "ownerVerdict": label["owner_verdict"],
        "verdictNote": label["verdict_note"],
    }


def _discovery_inventory(user_id: int, library_hash_value: str) -> tuple:
    """Count only eligible prose; a completed empty read is still current."""
    from agent.episodes import EXTRACTION_VERSION
    from agent.work_queue import MAX_ATTEMPTS
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """WITH inventory AS (
                   SELECT r.content,
                          (d.reflection_id IS NOT NULL
                           AND d.source_revision = r.discovery_revision
                           AND d.extraction_version = %s
                           AND d.library_hash = %s) AS is_current,
                          q.attempts, d.omitted_accounts, d.completed_at
                     FROM reflections r
                     LEFT JOIN discovery_reads d ON d.reflection_id = r.id
                     LEFT JOIN processing_queue q
                       ON q.source_type = 'discovery' AND q.source_id = r.id
                    WHERE r.user_id = %s AND r.evidence_eligible
                      AND length(btrim(coalesce(r.content, ''))) > 0
               )
               SELECT count(*),
                      count(*) FILTER (WHERE is_current),
                      count(*) FILTER (WHERE NOT is_current AND attempts IS NULL),
                      count(*) FILTER (WHERE attempts IS NOT NULL AND attempts < %s),
                      count(*) FILTER (WHERE attempts >= %s),
                      coalesce(sum(omitted_accounts) FILTER (WHERE is_current), 0),
                      max(completed_at) FILTER (WHERE is_current),
                      coalesce(sum(length(content))
                          FILTER (WHERE NOT is_current AND attempts IS NULL), 0)
                 FROM inventory""",
            (EXTRACTION_VERSION, library_hash_value, user_id,
             MAX_ATTEMPTS, MAX_ATTEMPTS),
        )
        counts = cur.fetchone()
        cur.execute(
            """SELECT count(*) FROM reflections WHERE user_id = %s
                 AND (NOT evidence_eligible OR length(btrim(coalesce(content, ''))) = 0)""",
            (user_id,),
        )
        excluded = cur.fetchone()[0]
        conn.commit()
    return (*counts, excluded)


@app.get("/api/discovery/status")
def discovery_status(user_id: int = Depends(get_current_user_id)):
    """Read-state and approximate cost; this never calls the model."""
    from agent.config import settings
    from agent.intelligence import Intelligence
    from agent.library import library_hash

    patterns = list(_library().values())
    digest = library_hash(patterns)
    (eligible, current, unread, pending, failed, omitted,
     completed, unread_chars, excluded) = _discovery_inventory(user_id, digest)
    batches = (len(patterns) + 4) // 5
    requests = int(unread) * (1 + batches)
    # An upper-bound label pass per unread entry; a read with no comparable
    # account skips it. Character/4 is the convention used by offline estimates.
    pattern_chars = sum(len(p.statement) + len(p.markers) for p in patterns)
    tokens_in = (int(unread_chars) + int(unread) * (batches * 300 + pattern_chars)) // 4
    estimate = Intelligence.estimate(
        settings.OPENAI_WORKER_MODEL, tokens_in, int(unread) * (1200 + batches * 2000))
    return {
        "eligibleEntries": int(eligible), "currentEntries": int(current),
        "unreadEntries": int(unread), "pendingEntries": int(pending),
        "failedEntries": int(failed), "excludedEntries": int(excluded),
        "omittedAccounts": int(omitted),
        "lastCompletedAt": completed.isoformat() if completed else None,
        "model": settings.OPENAI_WORKER_MODEL, "estimatedRequests": requests,
        "estimate": f"Approximate: {estimate}",
    }


@app.post("/api/discovery/refresh", status_code=202)
def refresh_discovery(body: DiscoveryRefresh, user_id: int = Depends(get_current_user_id)):
    """Explicit archive read, or explicit retry of parked discovery jobs."""
    from agent.episodes import EXTRACTION_VERSION
    from agent.library import library_hash
    from agent.observability.tracing import current_traceparent
    from agent.work_queue import MAX_ATTEMPTS, notify

    digest = library_hash(list(_library().values()))
    with db.connection() as conn, conn.cursor() as cur:
        if body.scope == "unread":
            cur.execute(
                """SELECT r.id
                     FROM reflections r
                     LEFT JOIN discovery_reads d ON d.reflection_id = r.id
                     LEFT JOIN processing_queue q
                       ON q.source_type = 'discovery' AND q.source_id = r.id
                    WHERE r.user_id = %s AND r.evidence_eligible
                      AND length(btrim(coalesce(r.content, ''))) > 0
                      AND q.id IS NULL
                      AND (d.reflection_id IS NULL
                           OR d.source_revision <> r.discovery_revision
                           OR d.extraction_version <> %s OR d.library_hash <> %s)
                    ORDER BY r.id FOR UPDATE OF r""",
                (user_id, EXTRACTION_VERSION, digest),
            )
            queued = 0
            for (source_id,) in cur.fetchall():
                # A concurrent refresh may have inserted its job while this
                # transaction waited for the source lock. Never bump that
                # existing job's generation on a repeated click.
                cur.execute(
                    """INSERT INTO processing_queue
                           (user_id, source_type, source_id, origin_traceparent)
                       VALUES (%s, 'discovery', %s, %s)
                       ON CONFLICT (source_type, source_id) DO NOTHING
                       RETURNING id""",
                    (user_id, source_id, current_traceparent()),
                )
                queued += cur.fetchone() is not None
        else:
            cur.execute(
                """UPDATE processing_queue q
                      SET attempts = 0, last_error = NULL, next_attempt_at = NOW(),
                          generation = q.generation + 1
                     FROM reflections r
                     LEFT JOIN discovery_reads d ON d.reflection_id = r.id
                    WHERE q.source_type = 'discovery' AND q.source_id = r.id
                      AND q.user_id = %s AND r.user_id = %s AND r.evidence_eligible
                      AND length(btrim(coalesce(r.content, ''))) > 0
                      AND q.attempts >= %s
                      AND (d.reflection_id IS NULL
                           OR d.source_revision <> r.discovery_revision
                           OR d.extraction_version <> %s OR d.library_hash <> %s)""",
                (user_id, user_id, MAX_ATTEMPTS, EXTRACTION_VERSION, digest),
            )
            queued = cur.rowcount
        conn.commit()
    if queued:
        notify()
    return {"queuedEntries": queued}


@app.get("/api/discovery/discussion")
def discovery_discussion(ref: str = Query(..., max_length=2048),
                         user_id: int = Depends(get_current_user_id)):
    """Current owner-scoped preview; only typed IDs and a snapshot enter from navigation."""
    from agent.evidence_ref import (CoLabelRef, DayRef, EvidenceNotCurrent,
                                    EvidenceNotFound, PatternRef)
    try:
        selected = discovery.resolve_discussion(user_id, ref)
    except EvidenceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EvidenceNotCurrent as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid evidence reference.") from exc
    pointer, evidence = selected["ref"], selected["evidence"]
    if isinstance(pointer, PatternRef) and pointer.kind == "pattern":
        data = {"pattern": _pattern_contract(evidence["pattern"]),
                "occasions": [_occasion_contract(o) for o in evidence["occasions"]],
                "distinctive": [{**row, "name": _library()[row["patternId"]].name}
                                for row in evidence["distinctive"]],
                "verdict": evidence["verdict"], "coverage": evidence["coverage"],
                "snapshot": evidence["snapshot"]}
    elif isinstance(pointer, PatternRef):
        data = {**evidence, "better": _occasion_contract(evidence["better"]),
                "worse": _occasion_contract(evidence["worse"])}
    elif isinstance(pointer, CoLabelRef):
        data = {"difference": evidence["difference"],
                "groups": {name: [_occasion_contract(o) for o in rows]
                           for name, rows in evidence["groups"].items()},
                "mixedExcluded": evidence["mixedExcluded"]}
    elif isinstance(pointer, DayRef):
        data = evidence
    else:
        raise HTTPException(status_code=422, detail="Invalid evidence reference.")
    body = {"ref": pointer.model_dump(), "title": selected["title"],
            "question": selected["question"], "evidence": data,
            "changed": selected["changed"]}
    _no_coordinates(body)
    return body


@app.get("/api/patterns")
def list_patterns(range: Literal["all", "30d", "90d"] = Query("all"),
                  user_id: int = Depends(get_current_user_id)):
    """All library lenses, with period-scoped source-backed writing."""
    rows, coverage = discovery.summaries_with_coverage(
        user_id, list(_library().values()), period=range)
    return {"coverage": coverage, "snapshot": discovery.writing_snapshot(user_id, period=range),
            "patterns": [
                {**_pattern_contract(s["pattern"]), "occasions": s["occasions"], "tones": s["tones"],
                 "reviewed": s["reviewed"], "rejected": s["rejected"], "labelledBy": s["labelledBy"],
                 "verdict": s["verdict"], "coverage": s["coverage"], "entryCount": s["entryCount"],
                 "recordedFrom": s["recordedFrom"], "recordedTo": s["recordedTo"],
                 "undatedAccountCount": s["undatedAccountCount"],
                 "examples": [_occasion_contract(o) for o in s["examples"]],
                 "snapshot": s["snapshot"]}
                for s in rows]}


@app.get("/api/patterns/{pattern_id}")
def get_pattern(pattern_id: str, range: Literal["all", "30d", "90d"] = Query("all"),
                user_id: int = Depends(get_current_user_id)):
    """One library lens and its period-scoped accounts, including rejected ones."""
    library = _library()
    if pattern_id not in library:
        raise HTTPException(status_code=404, detail="No such pattern.")
    d = discovery.detail(user_id, library[pattern_id], period=range)
    return {
        "pattern": _pattern_contract(d["pattern"]),
        "occasions": [_occasion_contract(o) for o in d["occasions"]],
        "distinctive": [{**row, "name": library[row["patternId"]].name}
                        for row in d["distinctive"]],
        "verdict": d["verdict"], "coverage": d["coverage"], "snapshot": d["snapshot"],
    }


@app.put("/api/patterns/{pattern_id}/occasions/{occasion_id}")
def put_occasion_verdict(pattern_id: str, occasion_id: int, body: OccasionVerdict,
                         user_id: int = Depends(get_current_user_id)):
    """Whether this occasion is really an instance of the pattern."""
    tone = {"owner_tone": body.ownerTone} if "ownerTone" in body.model_fields_set else {}
    if not discovery.set_occasion_verdict(
            user_id, pattern_id, occasion_id, body.verdict, body.note, **tone):
        raise HTTPException(status_code=404, detail="That occasion is not labelled with this pattern.")
    return {"ok": True}


@app.get("/api/differences")
def list_differences(range: Literal["all", "30d", "90d"] = Query("all"),
                     user_id: int = Depends(get_current_user_id)):
    return {"differences": discovery.differences(user_id, list(_library().values()), period=range),
            "reflections": [
                {**pair, "better": _occasion_contract(pair["better"]),
                 "worse": _occasion_contract(pair["worse"])}
                for pair in discovery.outcome_pairs(user_id, list(_library().values()), period=range)],
            "coverage": discovery.writing_coverage(user_id, period=range),
            "snapshot": discovery.writing_snapshot(user_id, period=range)}


@app.get("/api/differences/{pattern_id}/{other_pattern_id}")
def get_difference_detail(pattern_id: str, other_pattern_id: str,
                          range: Literal["all", "30d", "90d"] = Query("all"),
                          user_id: int = Depends(get_current_user_id)):
    library = _library()
    if pattern_id not in library or other_pattern_id not in library or pattern_id == other_pattern_id:
        raise HTTPException(status_code=404, detail="No such difference.")
    result = discovery.difference_detail(user_id, list(library.values()),
                                         pattern_id, other_pattern_id, period=range)
    if result is None:
        raise HTTPException(status_code=409, detail="This comparison has changed.")
    return {"difference": result["difference"],
            "groups": {key: [_occasion_contract(o) for o in group]
                       for key, group in result["groups"].items()},
            "mixedExcluded": result["mixedExcluded"]}


@app.get("/api/day-differences")
def list_day_differences(range: Literal["all", "30d", "90d"] = Query("all"),
                         user_id: int = Depends(get_current_user_id)):
    """Confirmed measurements alongside self-reports, never a cause."""
    from agent.day_differences import results
    result = results(user_id, period=range)
    body = {"differences": result["differences"], "diagnostics": result["diagnostics"]}
    _no_coordinates(body)
    return body


@app.get("/api/day-differences/{outcome}/{split}")
def get_day_difference_detail(outcome: str, split: str,
                              range: Literal["all", "30d", "90d"] = Query("all"),
                              user_id: int = Depends(get_current_user_id)):
    from agent.day_differences import OUTCOMES, SPLITS, detail_for_user
    if outcome not in OUTCOMES or split not in SPLITS:
        raise HTTPException(status_code=404, detail="No such day comparison.")
    result = detail_for_user(user_id, outcome, split, period=range)
    if result is None:
        raise HTTPException(status_code=409, detail="This comparison has changed.")
    _no_coordinates(result)
    return result


@app.put("/api/day-differences/{outcome}/{split}/verdict")
def put_day_difference_verdict(outcome: str, split: str, body: PatternVerdict,
                               user_id: int = Depends(get_current_user_id)):
    from agent.day_differences import set_verdict
    try:
        set_verdict(user_id, outcome, split, body.verdict, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="No such day comparison.") from exc
    return {"ok": True}


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
def _age_days(ts) -> int:
    """Calendar days, on this machine's clock, from a timestamp (datetime or ISO
    string) to today.

    An aware timestamp is converted to local time first. Dropping its tzinfo
    instead read a UTC time as local, so near midnight the count was off by one
    for anyone not on UTC.
    """
    if not ts:
        return 0
    try:
        dt = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
    except (ValueError, TypeError):
        return 0
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    return max(0, (date.today() - dt.date()).days)


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
    """POST /insights/:id/snooze body. Bounded: a negative length snoozed into
    the past, and a huge one overflowed timedelta into a 500."""
    days: int = Field(default=30, ge=1, le=3650)


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
    except IdeaDuplicate:
        raise HTTPException(status_code=409, detail=IDEA_DUPLICATE)
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
    statement: str | None = Field(default=None, max_length=STATEMENT_LIMIT)
    notes: str | None = Field(default=None, max_length=NOTES_LIMIT)


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


@app.get("/api/ideas/meanings/estimate")
def estimate_idea_meanings(user_id: int = Depends(get_current_user_id)):
    """What a same-meaning pass would send and cost. No model call."""
    return IdeaService(user_id).meaning_estimate()


@app.post("/api/ideas/meanings/discover")
def discover_idea_meanings(user_id: int = Depends(get_current_user_id)):
    """Propose pairs of accepted ideas that share one meaning. Owner-triggered."""
    return _analysis_result(IdeaService(user_id).discover_meanings())


class LinkConfirm(BaseModel):
    """Optional: the relation the owner names instead of the one proposed.
    `reverse` swaps which idea is which, for a relation with a direction."""
    kind: str | None = None
    reverse: bool = False


@app.post("/api/ideas/links/{link_id}/confirm")
def confirm_idea_link(link_id: int, body: LinkConfirm | None = None,
                      user_id: int = Depends(get_current_user_id)):
    body = body or LinkConfirm()
    try:
        return IdeaService(user_id).confirm_link(link_id, body.kind, body.reverse)
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


class FoldIdeaBody(BaseModel):
    intoId: int


@app.post("/api/ideas/{idea_id}/fold")
def fold_idea(idea_id: int, body: FoldIdeaBody, user_id: int = Depends(get_current_user_id)):
    """A proposal is an idea the owner already holds: move its quotes there."""
    return _idea_call(lambda: IdeaService(user_id).fold_into(idea_id, body.intoId))


@app.post("/api/ideas/{idea_id}/citations/reject")
def reject_idea_citations(
    idea_id: int, body: RejectCitationsBody, user_id: int = Depends(get_current_user_id),
):
    citation_ids = _citation_ids(body.citationIds)
    return _idea_call(lambda: IdeaService(user_id).reject_citations(idea_id, citation_ids))


@app.patch("/api/ideas/{idea_id}")
def update_idea(idea_id: int, body: UpdateIdeaBody, user_id: int = Depends(get_current_user_id)):
    if body.position is None and body.domain is None and body.statement is None and body.notes is None:
        raise HTTPException(status_code=422, detail="position, domain, statement or notes is required")
    _require_enum(body.position, IDEA_POSITIONS, "position")
    _require_enum(body.domain, IDEA_DOMAINS, "domain")
    if body.statement is not None and not body.statement.strip():
        raise HTTPException(status_code=422, detail="statement cannot be empty")
    return _idea_call(lambda: IdeaService(user_id).update(
        idea_id, position=body.position, domain=body.domain,
        statement=body.statement, notes=body.notes))


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

    entries = [r["content"] for r in this_week]
    key = review_letter.letter_key(facts, entries, with_findings, date.today())
    kept = review_letter.kept_letter(user_id, key)
    if kept is not None:
        return kept

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
    letter, keep = review_letter.compose_letter(
        facts, findings, entries, intelligence,
        [r.get("content_format") or "plain" for r in this_week],
    )
    if keep:
        review_letter.keep_letter(user_id, key, letter)
    return letter


@app.get("/api/review/latest")
def get_latest_review(user_id: int = Depends(get_current_user_id)):
    """ReviewWeek for the most recent 7-day window ending today."""
    week_start = date.today() - timedelta(days=6)
    return _build_review_week(user_id, week_start)


# ============================================================================
# OBSERVATORY (laptop only; the phone and tailnet may only send client events)
# ============================================================================

import psycopg2  # noqa: E402
from psycopg2 import pool as psycopg2_pool  # noqa: E402

from agent.observability import queries as obs_queries  # noqa: E402
from agent.observability import system_queries  # noqa: E402
from agent.observability.catalog import known as obs_known, mark_schema_unavailable, register_route, register_tables  # noqa: E402
from agent.observability.clients import ClientEvents, ingest as ingest_client_events  # noqa: E402
from agent.observability.hub import format_sse, hub, matches  # noqa: E402
from agent.observability.io import parts_for, strip_payload_attributes  # noqa: E402

_OBS_WINDOWS = {900, 3600, 21600, 86400, 604800, 1209600}
_DB_WINDOWS = {900, 3600, 21600, 86400}
_OBS_OFF = "The Observatory is switched off (OBS_ENABLED=false)."


def _window(window: int, allowed: set[int]) -> int:
    if window not in allowed:
        raise HTTPException(status_code=422, detail="unsupported window")
    return window


def _obs_required() -> None:
    if not obs.enabled():
        raise HTTPException(status_code=503, detail=_OBS_OFF)


def _obs_cursor(reader):
    _obs_required()
    try:
        with db.connection() as conn, conn.cursor() as cur:
            return reader(cur)
    except (psycopg2.Error, psycopg2_pool.PoolError):
        raise


def _obs_health():
    try:
        return _obs_cursor(obs_queries.health_now)
    except (psycopg2.Error, psycopg2_pool.PoolError):
        return obs_queries.health_memory()


@app.get("/api/observatory/overview")
def observatory_overview(window: int = 900):
    window = _window(window, _OBS_WINDOWS)
    _obs_required()
    try:
        with db.connection() as conn, conn.cursor() as cur:
            return obs_queries.overview(cur, window)
    except (psycopg2.Error, psycopg2_pool.PoolError):
        return obs_queries.overview_memory(window)


@app.get("/api/observatory/live")
async def observatory_live(
    request: Request,
    components: str = "",
    errors_only: bool = False,
    lifecycle: bool = False,
):
    _obs_required()
    wanted = {part for part in components.split(",") if part}
    subscription = hub.subscribe(asyncio.get_running_loop(), lifecycle=lifecycle)

    async def events():
        last_health = 0.0
        watermark = -1
        try:
            if lifecycle:
                snapshot = hub.lifecycle_snapshot()
                watermark = int(snapshot["sequence"])
                yield format_sse("snapshot", snapshot)
            else:
                for kind, item in hub.backlog(wanted, errors_only):
                    yield format_sse(kind, item)
            while True:
                if await request.is_disconnected():
                    break
                kind = None
                item = None
                try:
                    kind, item = await asyncio.wait_for(subscription.queue.get(), 5.0)
                except TimeoutError:
                    yield ": ping\n\n"
                now = asyncio.get_running_loop().time()
                if now - last_health >= 5:
                    yield format_sse("health", await run_in_threadpool(_obs_health))
                    last_health = now
                if kind is not None and item is not None:
                    sequence = item.get("sequence")
                    stale = lifecycle and isinstance(sequence, int) and sequence <= watermark
                    if not stale and matches(kind, item, wanted, errors_only):
                        yield format_sse(kind, item)
                if subscription.lagged:
                    yield format_sse("lagged", {"lagged": True})
                    subscription.lagged = False
        finally:
            hub.unsubscribe(subscription)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/api/observatory/traces")
def observatory_traces(
    component: str | None = None,
    status: str | None = None,
    min_ms: float = 0,
    q: str | None = None,
    window: int = 3600,
    limit: int = Query(default=100, le=500),
):
    window = _window(window, _OBS_WINDOWS)
    return _obs_cursor(lambda cur: obs_queries.traces(
        cur, component=component, status=status, min_ms=min_ms, q=q, window_s=window, limit=limit,
    ))


@app.get("/api/observatory/traces/{trace_id}")
def observatory_trace(trace_id: str = ApiPath(pattern="^[0-9a-f]{32}$")):
    detail = _obs_cursor(lambda cur: obs_queries.trace_detail(cur, trace_id))
    if detail is None:
        raise HTTPException(status_code=404, detail="No such trace.")
    return detail


@app.get("/api/observatory/operations")
def observatory_operations(window: int = 3600, component: str | None = None):
    window = _window(window, _OBS_WINDOWS)
    return _obs_cursor(lambda cur: obs_queries.operations(cur, window, component))


@app.get("/api/observatory/queue")
def observatory_queue():
    return _obs_cursor(obs_queries.queue_view)


@app.get("/api/observatory/database")
def observatory_database(window: int = 3600):
    window = _window(window, _DB_WINDOWS)
    return _obs_cursor(lambda cur: obs_queries.database_view(cur, window))


@app.get("/api/observatory/llm")
def observatory_llm(window: int = 86400):
    window = _window(window, _OBS_WINDOWS)
    return _obs_cursor(lambda cur: obs_queries.llm_view(cur, window))


@app.get("/api/observatory/analysis")
def observatory_analysis(limit: int = Query(default=20, le=100)):
    return _obs_cursor(lambda cur: obs_queries.analysis_view(cur, limit))


@app.get("/api/observatory/errors")
def observatory_errors(window: int = 86400):
    window = _window(window, _OBS_WINDOWS)
    return _obs_cursor(lambda cur: obs_queries.errors_view(cur, window))


@app.get("/api/observatory/logs")
def observatory_logs(
    level: str = "INFO",
    source: str | None = None,
    q: str | None = None,
    trace_id: str | None = None,
    window: int = 3600,
    limit: int = Query(default=200, le=1000),
):
    window = _window(window, _OBS_WINDOWS)
    return _obs_cursor(lambda cur: obs_queries.logs(
        cur, level=level, source=source, q=q, trace_id=trace_id, window_s=window, limit=limit,
    ))


@app.get("/api/observatory/samples")
def observatory_samples(names: str = "", window: int = 3600):
    window = _window(window, _OBS_WINDOWS)
    chosen = [part for part in names.split(",") if part]
    return _obs_cursor(lambda cur: obs_queries.samples(cur, chosen, window))


@app.get("/api/observatory/clients")
def observatory_clients():
    return _obs_cursor(obs_queries.clients_view)


@app.post("/api/observatory/client-events")
def observatory_client_events(body: ClientEvents):
    return {"accepted": ingest_client_events(body)}


def _obs_trace_filter(trace_id: str | None) -> str | None:
    if trace_id is None:
        return None
    if len(trace_id) != 32 or any(ch not in "0123456789abcdef" for ch in trace_id):
        raise HTTPException(status_code=422, detail="trace_id must be 32 lowercase hex characters.")
    return trace_id


def _obs_invocation(record: dict, source: str, logs: list | None = None, related: list | None = None) -> dict:
    attributes = record.get("attributes") if isinstance(record.get("attributes"), dict) else {}
    parts = parts_for(
        str(record.get("name") or ""),
        str(record.get("component") or ""),
        attributes,
        status=str(record.get("status") or "ok"),
        status_message=record.get("status_message"),
        running=record.get("status") == "running",
    )
    inputs, outputs = system_queries.split_parts(parts)
    span = {
        "trace_id": record.get("trace_id"),
        "span_id": record.get("span_id"),
        "parent_span_id": record.get("parent_span_id"),
        "name": record.get("name"),
        "component": record.get("component"),
        "kind": record.get("kind"),
        "started_at": record.get("started_at"),
        "duration_ms": record.get("duration_ms"),
        "self_ms": record.get("self_ms"),
        "status": record.get("status"),
        "status_message": record.get("status_message"),
        "attrs": record.get("attrs") or {},
        "module_id": record.get("module_id"),
        "parent_module_id": record.get("parent_module_id"),
        "links": record.get("links") or [],
    }
    return {
        "span": span,
        "io": {"inputs": inputs, "outputs": outputs},
        "attributes": strip_payload_attributes(attributes),
        "events": record.get("events") or [],
        "logs": logs or [],
        "related": related or [],
        "source": source,
    }


@app.get("/api/observatory/system")
def observatory_system(window: int = 3600, trace_id: str | None = None):
    window = _window(window, _OBS_WINDOWS)
    _obs_required()
    chosen = _obs_trace_filter(trace_id)
    try:
        with db.connection() as conn, conn.cursor() as cur:
            return system_queries.system_view(cur, window, chosen)
    except (psycopg2.Error, psycopg2_pool.PoolError):
        return system_queries.system_memory(window, chosen)


@app.get("/api/observatory/module-calls")
def observatory_module_calls(
    module_id: str,
    window: int = 3600,
    trace_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
):
    window = _window(window, _OBS_WINDOWS)
    _obs_required()
    if not module_id or len(module_id) > 300:
        raise HTTPException(status_code=422, detail="module_id must be 1-300 characters.")
    chosen = _obs_trace_filter(trace_id)
    try:
        with db.connection() as conn, conn.cursor() as cur:
            result = system_queries.module_calls(cur, module_id, window, chosen, limit)
    except (psycopg2.Error, psycopg2_pool.PoolError):
        if not obs_known(module_id):
            raise HTTPException(status_code=503, detail="Stored invocation data is temporarily unavailable.")
        return system_queries.module_calls_memory(module_id, chosen, limit)
    if not obs_known(module_id) and not result["recent"] and not result["active"]:
        raise HTTPException(status_code=404, detail="Unknown Observatory module.")
    return result


@app.get("/api/observatory/spans/{trace_id}/{span_id}")
def observatory_span(
    trace_id: str = ApiPath(pattern="^[0-9a-f]{32}$"),
    span_id: str = ApiPath(pattern="^[0-9a-f]{16}$"),
):
    _obs_required()
    cached = hub.invocation_record(trace_id, span_id)
    if cached is not None:
        return _obs_invocation(cached, "memory")
    try:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT trace_id, span_id, parent_span_id, name, component, kind, started_at,
                       duration_ms, self_ms, status, status_message, attributes, events, links,
                       module_id, parent_module_id
                FROM obs_spans WHERE trace_id = %s AND span_id = %s
                """,
                (trace_id, span_id),
            )
            row = cur.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Invocation details are not currently available.")
            record = {
                "trace_id": row[0], "span_id": row[1], "parent_span_id": row[2], "name": row[3],
                "component": row[4], "kind": row[5], "started_at": row[6].strftime("%Y-%m-%dT%H:%M:%S.%fZ") if hasattr(row[6], "strftime") else row[6],
                "duration_ms": row[7], "self_ms": row[8], "status": row[9], "status_message": row[10],
                "attributes": row[11] or {}, "events": row[12] or [], "links": row[13] or [],
                "module_id": row[14], "parent_module_id": row[15],
            }
            cur.execute(
                """
                SELECT at, source, level, logger, message, exception, trace_id, span_id, attributes
                FROM obs_logs WHERE trace_id = %s AND span_id = %s ORDER BY at
                """,
                (trace_id, span_id),
            )
            logs = [
                {
                    "at": item[0].strftime("%Y-%m-%dT%H:%M:%S.%fZ") if hasattr(item[0], "strftime") else item[0],
                    "source": item[1], "level": item[2], "logger": item[3], "message": item[4],
                    "exception": item[5], "trace_id": item[6], "span_id": item[7], "attributes": item[8] or {},
                }
                for item in cur.fetchall()
            ]
            cur.execute(
                f"""
                SELECT {system_queries.summary_select()}
                FROM obs_spans
                WHERE trace_id = %s AND (
                    parent_span_id = %s OR attributes->>'iris.db.query_span_id' = %s
                )
                ORDER BY started_at
                LIMIT 50
                """,
                (trace_id, span_id, span_id),
            )
            related = [system_queries.summary_row(item) for item in cur.fetchall()]
    except HTTPException:
        raise
    except (psycopg2.Error, psycopg2_pool.PoolError):
        raise HTTPException(status_code=503, detail="Stored invocation data is temporarily unavailable.")
    return _obs_invocation(record, "database", logs, related)


def _publish_route_catalog() -> None:
    for route in app.routes:
        path = getattr(route, "path", None)
        endpoint = getattr(route, "endpoint", None)
        methods = getattr(route, "methods", None) or set()
        if not isinstance(path, str):
            continue
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            register_route(method, path, endpoint)


def _publish_table_catalog() -> None:
    try:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position
                """
            )
            register_tables(cur.fetchall())
    except (psycopg2.Error, psycopg2_pool.PoolError):
        mark_schema_unavailable()


_publish_route_catalog()


# ============================================================================
# SPA FALLBACK (serve client-side routes from the built frontend)
# ============================================================================
# Registered last so it never shadows /api/*, /assets, or /health. Active only
# when the SPA is built (frontend/dist), so dev (Vite on :5173) is unaffected.
if os.path.exists(os.path.join(FRONTEND_DIST, "index.html")):

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        """Return index.html for unknown non-API paths so React Router can route."""
        if full_path.startswith(("api/", "assets/")) or full_path in ("api", "health"):
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"), headers=_SPA_HEADERS)


# ============================================================================
# RUN THE APP (for local testing)
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
