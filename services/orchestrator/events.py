"""Internal HTTP server + event log.

- POST /event/presence {"person": "jose"} -> greeting via TTS (Fase 5),
  honoring the DND flag and leaving hysteresis to the vision service.
- POST /dnd {"enabled": true|false}        -> toggled from the panel.
- GET  /health
- Event log: /logs/events.db (SQLite). The panel reads it; the nightly
  reflection job consumes the day's transcripts from here.

Auth: /event/presence and /dnd require the shared secret EVENTS_SECRET
(header X-Jarvis-Events-Secret). Other containers on the compose network (n8n
runs arbitrary workflow code) must not be able to toggle DND or trigger TTS.
Fail-closed: if EVENTS_SECRET is unset, those endpoints are refused.
"""

import hmac
import json
import os
import sqlite3
import time
from pathlib import Path

from aiohttp import web
from loguru import logger

from pipecat.frames.frames import TTSSpeakFrame

DB_PATH = Path("/logs/events.db")
SECRET = os.getenv("EVENTS_SECRET", "")
_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH)
        _conn.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            " ts REAL, kind TEXT, payload TEXT)"
        )
        _conn.commit()
    return _conn


def log_event(kind: str, payload: dict) -> None:
    try:
        _db().execute(
            "INSERT INTO events VALUES (?, ?, ?)",
            (time.time(), kind, json.dumps(payload, ensure_ascii=False)),
        )
        _db().commit()
    except Exception as e:
        logger.warning(f"event log failed: {e}")


def _authorized(request: web.Request) -> bool:
    if not SECRET:
        return False                       # fail-closed: sin secreto no se atiende
    provided = request.headers.get("X-Jarvis-Events-Secret", "")
    return hmac.compare_digest(provided, SECRET)


async def start(task, security, *, port: int = 8070) -> None:
    if not SECRET:
        logger.warning("EVENTS_SECRET no definido: /dnd y /event/presence quedan deshabilitados")

    async def presence(request: web.Request) -> web.Response:
        if not _authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        data = await request.json()
        person = data.get("person", "alguien")
        log_event("presence", data)
        if security.dnd:
            return web.json_response({"status": "dnd"})
        # TODO(Fase 5): personalize via persona/relacion.md and time of day.
        await task.queue_frames([TTSSpeakFrame(f"Bienvenido a casa, {person}.")])
        return web.json_response({"status": "greeted"})

    async def dnd(request: web.Request) -> web.Response:
        if not _authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        data = await request.json()
        security.dnd = bool(data.get("enabled"))
        log_event("dnd", {"enabled": security.dnd})
        return web.json_response({"dnd": security.dnd})

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_post("/event/presence", presence)
    app.router.add_post("/dnd", dnd)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logger.info(f"events server on :{port}")
