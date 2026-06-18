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

import asyncio
import hmac
import json
import os
import subprocess
import time
import sqlite3
from pathlib import Path
from urllib.parse import quote

from aiohttp import web
from loguru import logger

from pipecat.frames.frames import TTSSpeakFrame

DB_PATH = Path("/logs/events.db")
SECRET = os.getenv("EVENTS_SECRET", "")
_conn: sqlite3.Connection | None = None
_gate = None                     # ProactiveGate (Fase B): routing voz/Telegram por presencia
_glasses = None                  # cerebro propio del canal "gafas/app iOS" (historia aislada)


def _brain():
    """Cerebro de texto reutilizable (mismas tools+memoria que Telegram), instancia
    dedicada al canal de la app/gafas para no mezclar su historial con el de Telegram."""
    global _glasses
    if _glasses is None:
        from telegram_agent import TelegramAgent
        _glasses = TelegramAgent()
    return _glasses


def _synth_sync(text: str) -> bytes:
    """Sintetiza con la voz local de Jarvis (Piper carlfm-high) -> WAV bytes."""
    voice = os.getenv("PIPER_VOICE", "es_ES-carlfm-high")
    out = "/tmp/glasses_tts.wav"
    subprocess.run(["/usr/local/bin/piper", "--model", f"/models/piper/{voice}.onnx",
                    "--output_file", out], input=text.encode(), capture_output=True, timeout=30)
    return Path(out).read_bytes()


def set_gate(gate) -> None:
    """Lo llama bot.py tras crear el ProactiveGate; permite a /event/* enrutar por presencia."""
    global _gate
    _gate = gate


def _greeting() -> str:
    from datetime import datetime
    h = datetime.now().hour
    saludo = "Buenos días" if 5 <= h < 12 else ("Buenas tardes" if 12 <= h < 20 else "Buenas noches")
    return f"{saludo}, señor. Bienvenido."


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
        """Latido del sensor de visión (Fase B). Mantiene el estado presente/ausente y
        saluda SOLO en la transición ausente->presente (con cooldown). Acepta:
        {"person":"jose"} (visto), o {"beat":true} (vivo pero sin ver a nadie)."""
        if not _authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        data = await request.json()
        person = data.get("person")
        log_event("presence", data)
        from proactive import PRESENCE, GREET_COOLDOWN
        was_present = PRESENCE.is_present(person) if person else True
        PRESENCE.beat(person)                       # refresca last_seen / vision viva
        if person and not was_present:              # llegada real (estaba ausente)
            if time.time() - PRESENCE.last_greeted.get(person, 0) >= GREET_COOLDOWN:
                PRESENCE.last_greeted[person] = time.time()
                if _gate is not None:
                    await _gate.say(_greeting(), key=f"greet:{person}", tier="ambient", person=person)
                elif not security.dnd:
                    await task.queue_frames([TTSSpeakFrame(_greeting())])
        return web.json_response({"status": "ok", "present": True})

    async def say(request: web.Request) -> web.Response:
        """Voz proactiva: hace que Jarvis diga un texto (lo usa el puente de
        investigación al terminar). Enruta por presencia vía el gate (presente->voz,
        ausente->Telegram); si no hay gate aún, cae al comportamiento previo."""
        if not _authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        data = await request.json()
        text = (data.get("text") or "").strip()
        if not text:
            return web.json_response({"error": "no text"}, status=400)
        log_event("proactive_say", {"text": text[:300]})
        if _gate is not None:
            ok = await _gate.say(text, tier="info")
            return web.json_response({"status": "routed" if ok else "suppressed"})
        try:
            import telegram
            await telegram.send(text)
        except Exception:
            pass
        if security.dnd:
            return web.json_response({"status": "dnd"})
        await task.queue_frames([TTSSpeakFrame(text)])
        return web.json_response({"status": "spoken"})

    async def dnd(request: web.Request) -> web.Response:
        if not _authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        data = await request.json()
        security.dnd = bool(data.get("enabled"))
        log_event("dnd", {"enabled": security.dnd})
        return web.json_response({"dnd": security.dnd})

    async def ask(request: web.Request) -> web.Response:
        """Canal app/gafas (texto): {text} -> respuesta del cerebro {reply}.
        Para clientes que hacen STT on-device (Apple Speech) y TTS propio."""
        if not _authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        data = await request.json()
        text = (data.get("text") or "").strip()
        if not text:
            return web.json_response({"error": "no text"}, status=400)
        log_event("glasses_ask", {"text": text[:300]})
        reply = await _brain()._think(text)
        return web.json_response({"reply": reply})

    async def voice(request: web.Request) -> web.Response:
        """Canal app/gafas (voz E2E): audio crudo -> Whisper -> cerebro -> Piper carlfm
        -> WAV con la voz de Jarvis (se reproduce por las gafas). Transcript y respuesta
        en cabeceras (url-encoded) para depurar/mostrar en la app."""
        if not _authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        raw = await request.read()
        if not raw:
            return web.json_response({"error": "no audio"}, status=400)
        path = f"/tmp/glasses_in_{int(time.time()*1000)}"
        Path(path).write_bytes(raw)
        import voice_notes
        try:
            text = await voice_notes.transcribe(path)
        except Exception as e:
            logger.warning(f"[gafas] transcripción: {e}")
            text = ""
        finally:
            try:
                os.remove(path)
            except Exception:
                pass
        if not text:
            return web.json_response({"error": "no_speech"}, status=422)
        log_event("glasses_voice", {"text": text[:300]})
        reply = await _brain()._think(text)
        wav = await asyncio.to_thread(_synth_sync, reply)
        return web.Response(body=wav, content_type="audio/wav",
                            headers={"X-Transcript": quote(text[:300]), "X-Reply": quote(reply[:500])})

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    app = web.Application(client_max_size=20 * 1024 * 1024)   # audios de la app hasta ~20MB
    app.router.add_post("/event/presence", presence)
    app.router.add_post("/event/say", say)
    app.router.add_post("/dnd", dnd)
    app.router.add_post("/ask", ask)
    app.router.add_post("/voice", voice)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logger.info(f"events server on :{port}")
