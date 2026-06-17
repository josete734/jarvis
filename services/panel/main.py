"""Control panel — FastAPI + HTMX (PLAN_FINAL §9.2, Fase 6).

Auth: el contenedor escucha en 127.0.0.1 y solo lo alcanzan dos caminos que
inyectan identidad — `tailscale serve` (tailnet) o Cloudflare Tunnel + Access
(internet). El middleware exige email ∈ PANEL_ALLOWED_USERS (fail-closed).
PANEL_PASSWORD es segundo factor para acciones mutantes (persona, tools, DND).

Funciones: estado de servicios + métricas del host (en vivo, htmx), eventos,
editor de las personas, toggle de tools y de "no molestar".
Pendiente: dashboard de latencias por etapa (depende de la voz).
"""

import hmac
import html
import json
import os
import sqlite3
import time
from pathlib import Path

import aiohttp
import yaml
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import docker_client

ALLOWED = {u.strip() for u in os.getenv("PANEL_ALLOWED_USERS", "").split(",") if u.strip()}
PASSWORD = os.getenv("PANEL_PASSWORD", "")
PERSONA_DIR = Path("/persona")
PERSONA_FILES = {                                   # clave -> (fichero, etiqueta)
    "jarvis": ("jarvis.md", "Personalidad (jarvis.md)"),
    "perfil": ("perfil_usuario.md", "Perfil del usuario (perfil_usuario.md)"),
    "relacion": ("relacion.md", "Relación (relacion.md)"),
}
TOOLS_YAML = Path("/config/tools.yaml")
EVENTS_DB = Path("/logs/events.db")
ORCHESTRATOR = os.getenv("ORCHESTRATOR_EVENTS", "http://orchestrator:8070")
EVENTS_SECRET = os.getenv("EVENTS_SECRET", "")

# Estado de voz en tiempo real: lo escribe el orchestrator (VoiceStateObserver)
# en el volumen compartido /logs. Si el fichero falta o está rancio (> stale),
# caemos a "EN ESCUCHA" — así nunca se queda "RESPONDIENDO" pegado.
VOICE_STATE_FILE = Path("/logs/voice_state.json")
VOICE_STALE_SECS = 10.0
# enum del pipeline -> presentación: (label, sub por defecto, active, anim_hint)
_VOICE_MAP = {
    "idle":         ("EN ESCUCHA",     "A la espera de «hey Mycroft».", False, "idle"),
    "wake":         ("DESPIERTO",      "Te escucho, señor.",           True,  "wake"),
    "listening":    ("ESCUCHANDO",     "Le sigo, dígame.",             True,  "listen"),
    "transcribing": ("TRANSCRIBIENDO", "Pasando su voz a texto…",      True,  "think"),
    "thinking":     ("PENSANDO",       "Consultando al modelo…",       True,  "think"),
    "tool":         ("EN ACCIÓN",      "Usando una herramienta…",      True,  "tool"),
    "speaking":     ("RESPONDIENDO",   "",                             True,  "speak"),
}

app = FastAPI(title="jarvis-panel")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.middleware("http")
async def identity(request: Request, call_next):
    # /hud y /api/hud: kiosko de solo-lectura en el monitor local (sin login).
    if request.url.path in ("/health", "/favicon.ico", "/hud", "/api/hud", "/api/agenda",
                            "/api/briefing", "/spotify/login", "/spotify/callback",
                            "/api/propuesta/decision"):     # interno: auth por EVENTS_SECRET
        return await call_next(request)
    # Identidad por dos vías, ambas verificadas contra PANEL_ALLOWED_USERS (fail-closed):
    #   - Tailscale-User-Login: acceso por el tailnet (`tailscale serve`).
    #   - Cf-Access-Authenticated-User-Email: acceso por internet vía Cloudflare
    #     Tunnel + Access (Cloudflare ya exigió login antes de llegar aquí).
    # Endurecimiento futuro: validar el JWT Cf-Access-Jwt-Assertion contra las
    # claves públicas de Cloudflare (defensa en profundidad).
    user = (
        request.headers.get("Tailscale-User-Login", "")
        or request.headers.get("Cf-Access-Authenticated-User-Email", "")
    )
    if not ALLOWED or user not in ALLOWED:
        return HTMLResponse(
            f"<h1>403</h1><p>Identidad no autorizada: {html.escape(user) or '(sin header)'}.</p>"
            "<p>Entra por el tailnet (<code>tailscale serve</code>) o por "
            "<code>jarvis.calahierbas.casa</code> (Cloudflare Access).</p>",
            status_code=403,
        )
    request.state.user = user
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Cabeceras de seguridad en todas las respuestas (panel expuesto por internet)."""
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path in ("/hud", "/api/hud"):
        # Kiosko local: permite Google Fonts (Geist) + script inline del HUD.
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: https://*.scdn.co; connect-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "script-src 'self' 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"
        )
    else:
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        )
    return resp


def _check_password(pw: str) -> bool:
    return bool(PASSWORD) and pw == PASSWORD


def _recent_events(limit: int = 30) -> list[dict]:
    if not EVENTS_DB.exists():
        return []
    conn = sqlite3.connect(EVENTS_DB)
    try:
        rows = conn.execute(
            "SELECT ts, kind, payload FROM events ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
    return [
        {"ts": ts, "time": time.strftime("%d %b %H:%M:%S", time.localtime(ts)), "kind": k, "payload": p}
        for ts, k, p in rows
    ]


def _host_metrics() -> dict:
    """Salud del host (solo stdlib). El contenedor ve /proc del host: load, RAM y
    discos montados reflejan la máquina (M70q). Disco: /logs=NVMe, /mnt/storage=SATA."""
    m = {"load": None, "cores": os.cpu_count(), "mem": None, "disks": []}
    try:
        la = os.getloadavg()
        m["load"] = f"{la[0]:.2f}  {la[1]:.2f}  {la[2]:.2f}"
    except Exception:
        pass
    try:
        mi = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, _, v = line.partition(":")
            if v:
                mi[k] = int(v.strip().split()[0])      # kB
        total, avail = mi.get("MemTotal", 0), mi.get("MemAvailable", 0)
        if total:
            used = total - avail
            m["mem"] = {"used": round(used / 1048576, 1), "total": round(total / 1048576, 1),
                        "pct": round(used * 100 / total)}
    except Exception:
        pass
    for label, path in (("Sistema · NVMe", "/logs"), ("Almacén · SATA", "/mnt/storage")):
        try:
            s = os.statvfs(path)
            total = s.f_blocks * s.f_frsize
            used = (s.f_blocks - s.f_bfree) * s.f_frsize    # real (excluye reservados), como df
            avail = s.f_bavail * s.f_frsize
            if total:
                m["disks"].append({"label": label, "used": round(used / 1073741824),  # GiB, como df
                                   "total": round(total / 1073741824),
                                   "pct": round(used * 100 / (used + avail)) if (used + avail) else 0})
        except Exception:
            pass
    return m


def _personas() -> list[dict]:
    out = []
    for key, (fname, label) in PERSONA_FILES.items():
        p = PERSONA_DIR / fname
        out.append({"key": key, "label": label,
                    "content": p.read_text(encoding="utf-8") if p.exists() else ""})
    return out


def _rel_time(secs: float) -> str:
    secs = int(max(0, secs))
    if secs < 60:    return "ahora mismo"
    if secs < 3600:  return f"hace {secs // 60} min"
    if secs < 86400: return f"hace {secs // 3600} h"
    return f"hace {secs // 86400} d"


def _fallback_voice() -> dict:
    lbl, sub, active, anim = _VOICE_MAP["idle"]
    return {"state": "idle", "state_label": lbl, "sub": sub,
            "active": active, "anim": anim, "level": 0.0, "fresh": False}


def _voice_state() -> dict:
    """Lee /logs/voice_state.json (lo escribe el orchestrator con os.replace).
    Frescura por mtime: si falta o > VOICE_STALE_SECS => EN ESCUCHA. Esto evita
    el "RESPONDIENDO" pegado cuando Jarvis lleva tiempo callado o el orq. cae."""
    try:
        age = time.time() - VOICE_STATE_FILE.stat().st_mtime
        if age > VOICE_STALE_SECS:
            return _fallback_voice()
        data = json.loads(VOICE_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return _fallback_voice()

    state = (data.get("state") or "idle").lower()
    lbl, sub_def, active, anim = _VOICE_MAP.get(state, _VOICE_MAP["idle"])
    sub = sub_def
    if state == "transcribing" and data.get("last_user_text"):
        sub = data["last_user_text"][:80]
    elif state == "speaking" and data.get("last_bot_text"):
        sub = data["last_bot_text"][:80]
    elif state == "tool" and data.get("tool"):
        sub = data["tool"]
    return {
        "state": state, "state_label": lbl, "sub": sub,
        "active": active, "anim": anim,
        "level": float(data.get("level") or 0.0),
        "last_wake": data.get("last_wake"),
        "model": data.get("model"),
        "tool": data.get("tool") or "",
        "ttfb": data.get("ttfb") or {},
        "fresh": True,
    }


def _voice_telemetry() -> dict:
    """'Oídos hoy' y 'último oído' leyendo events.db directo (barato)."""
    out = {"wakes_today": 0, "convos_today": 0, "last_heard": None}
    if not EVENTS_DB.exists():
        return out
    n = time.localtime()
    midnight = time.mktime((n.tm_year, n.tm_mon, n.tm_mday, 0, 0, 0, 0, 0, -1))
    conn = sqlite3.connect(EVENTS_DB)
    try:
        out["wakes_today"] = conn.execute(
            "SELECT COUNT(*) FROM events WHERE ts>=? AND kind IN ('wake','user_said')",
            (midnight,),
        ).fetchone()[0]
        out["convos_today"] = conn.execute(
            "SELECT COUNT(*) FROM events WHERE ts>=? AND kind='user_said'", (midnight,),
        ).fetchone()[0]
        row = conn.execute(
            "SELECT ts FROM events WHERE kind IN ('wake','user_said') ORDER BY ts DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if row:
        out["last_heard"] = _rel_time(time.time() - row[0])
    return out


# --- Tiempo (open-meteo, sin API key) — cacheado para no pegar en cada poll ---
WEATHER_LAT = os.getenv("HUD_WEATHER_LAT", "41.1549")    # Reus por defecto
WEATHER_LON = os.getenv("HUD_WEATHER_LON", "1.1087")
WEATHER_PLACE = os.getenv("HUD_WEATHER_PLACE", "Reus")
_WEATHER = {"ts": 0.0, "data": None}
# WMO weather code -> (texto es, icono)
_WMO = {
    0: ("Despejado", "☀"), 1: ("Casi despejado", "🌤"), 2: ("Parcial. nuboso", "⛅"),
    3: ("Nublado", "☁"), 45: ("Niebla", "🌫"), 48: ("Niebla", "🌫"),
    51: ("Llovizna", "🌦"), 53: ("Llovizna", "🌦"), 55: ("Llovizna", "🌦"),
    61: ("Lluvia débil", "🌧"), 63: ("Lluvia", "🌧"), 65: ("Lluvia fuerte", "🌧"),
    71: ("Nieve", "🌨"), 73: ("Nieve", "🌨"), 75: ("Nieve", "🌨"),
    80: ("Chubascos", "🌦"), 81: ("Chubascos", "🌧"), 82: ("Chubascos", "⛈"),
    95: ("Tormenta", "⛈"), 96: ("Tormenta", "⛈"), 99: ("Tormenta", "⛈"),
}


async def _weather() -> dict | None:
    now = time.time()
    if _WEATHER["data"] is not None and (now - _WEATHER["ts"]) < 900:   # cache 15 min
        return _WEATHER["data"]
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
           "&current=temperature_2m,weather_code"
           "&daily=temperature_2m_max,temperature_2m_min,weather_code"
           "&timezone=auto&forecast_days=3")
    try:
        import datetime as _wdt
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=4)) as r:
                j = await r.json()
        cur, day = j.get("current", {}), j.get("daily", {})
        code = int(cur.get("weather_code", 0))
        desc, icon = _WMO.get(code, ("—", "•"))
        # Previsión por días (HOY/MAÑ/abreviatura)
        times = day.get("time", []) or []
        dmax, dmin = day.get("temperature_2m_max", []), day.get("temperature_2m_min", [])
        dcode = day.get("weather_code", [])
        wd = ["LUN", "MAR", "MIÉ", "JUE", "VIE", "SÁB", "DOM"]
        today = _wdt.date.today()
        days = []
        for i in range(min(3, len(times))):
            try:
                dd = _wdt.date.fromisoformat(times[i]); diff = (dd - today).days
                lab = "HOY" if diff == 0 else "MAÑ" if diff == 1 else wd[dd.weekday()]
            except Exception:
                lab = ""
            dco = int(dcode[i]) if i < len(dcode) else 0
            days.append({"label": lab, "icon": _WMO.get(dco, ("—", "•"))[1],
                         "max": round(dmax[i]), "min": round(dmin[i])})
        data = {
            "place": WEATHER_PLACE,
            "temp": round(cur.get("temperature_2m")),
            "max": round((dmax or [None])[0]),
            "min": round((dmin or [None])[0]),
            "desc": desc, "icon": icon, "days": days,
        }
        _WEATHER.update(ts=now, data=data)
        return data
    except Exception:
        return _WEATHER["data"]   # último bueno si falla (o None)


# --- Spotify "Now Playing" (widget flotante; la API es global a la cuenta) ---
import urllib.parse as _uparse
SPOTIFY_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT = os.getenv("SPOTIFY_REDIRECT", "https://jarvis.calahierbas.casa/spotify/callback")
_SPOTIFY_REFRESH_FILE = Path("/config/spotify_refresh.txt")
_SPOTIFY = {"access": "", "exp": 0.0}


def _spotify_refresh() -> str:
    r = os.getenv("SPOTIFY_REFRESH_TOKEN", "").strip()
    if r:
        return r
    try:
        return _SPOTIFY_REFRESH_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


async def _spotify_token() -> str | None:
    refresh = _spotify_refresh()
    if not (SPOTIFY_ID and SPOTIFY_SECRET and refresh):
        return None
    now = time.time()
    if _SPOTIFY["access"] and now < _SPOTIFY["exp"] - 30:
        return _SPOTIFY["access"]
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post("https://accounts.spotify.com/api/token", data={
                "grant_type": "refresh_token", "refresh_token": refresh,
                "client_id": SPOTIFY_ID, "client_secret": SPOTIFY_SECRET,
            }, timeout=aiohttp.ClientTimeout(total=8)) as r:
                j = await r.json()
        tok = j.get("access_token")
        if tok:
            _SPOTIFY.update(access=tok, exp=now + float(j.get("expires_in", 3600)))
            return tok
    except Exception:
        pass
    return None


# El HUD sondea /api/hud cada ~700ms; sin caché pegábamos a Spotify miles de veces/h
# -> HTTP 429 "Too many requests" -> el widget no recibía nada. Caché corta (la música
# cambia poco en segundos) + backoff largo ante 429. Sirve el último valor bueno mientras.
_SPOTIFY_NP = {"data": None, "ts": 0.0, "ttl": 8.0}


async def _spotify() -> dict | None:
    now = time.time()
    if now - _SPOTIFY_NP["ts"] < _SPOTIFY_NP["ttl"]:
        return _SPOTIFY_NP["data"]
    tok = await _spotify_token()
    if not tok:
        _SPOTIFY_NP.update(data=None, ts=now, ttl=30.0)
        return None
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("https://api.spotify.com/v1/me/player/currently-playing",
                             headers={"Authorization": "Bearer " + tok},
                             timeout=aiohttp.ClientTimeout(total=6)) as r:
                if r.status == 429:                       # rate-limited: backoff, conserva lo último
                    _SPOTIFY_NP.update(ts=now, ttl=float(r.headers.get("Retry-After", "30")) + 1)
                    return _SPOTIFY_NP["data"]
                if r.status == 204:                       # nada sonando
                    _SPOTIFY_NP.update(data={"playing": False}, ts=now, ttl=8.0)
                    return _SPOTIFY_NP["data"]
                if r.status != 200:
                    _SPOTIFY_NP.update(ts=now, ttl=15.0)
                    return _SPOTIFY_NP["data"]
                j = await r.json()
    except Exception:
        _SPOTIFY_NP.update(ts=now, ttl=15.0)
        return _SPOTIFY_NP["data"]
    item = j.get("item") or {}
    if not item:
        _SPOTIFY_NP.update(data={"playing": False}, ts=now, ttl=8.0)
        return _SPOTIFY_NP["data"]
    imgs = (item.get("album") or {}).get("images") or []
    data = {
        "playing": bool(j.get("is_playing")),
        "title": item.get("name", ""),
        "artist": ", ".join(a.get("name", "") for a in item.get("artists", [])),
        "art": imgs[0]["url"] if imgs else "",
        "progress": j.get("progress_ms", 0),
        "duration": item.get("duration_ms", 0),
    }
    _SPOTIFY_NP.update(data=data, ts=now, ttl=8.0)
    return data


# --- Agenda: uno o VARIOS feeds ICS secretos (Google Calendar iCal privado, CalDAV…) ---
import asyncio
import datetime as _dt
import re as _re
# Acepta varias URLs separadas por coma/espacio/salto de línea (cada cal con su color en el HUD)
CAL_URLS = [u for u in _re.split(r"[\s,]+", os.getenv("HUD_CALENDAR_ICS", "")) if u.startswith("http")]
_CAL = {"ts": 0.0, "data": None}


async def _fetch_ics(session, url: str) -> bytes:
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as r:
        return await r.read()


async def _calendar() -> list | None:
    """Próximos eventos combinando todas las URLs ICS de HUD_CALENDAR_ICS. None si no hay
    ninguna. Cacheado 5 min; expande recurrencias (RRULE); cada evento lleva 'cal' (índice
    de calendario) para colorearlo en el HUD."""
    if not CAL_URLS:
        return None
    now = time.time()
    if _CAL["data"] is not None and (now - _CAL["ts"]) < 120:   # 120s: refresco ágil (el cliente además filtra a tiempo real)
        return _CAL["data"]
    try:
        import icalendar
        import recurring_ical_events
        start = _dt.datetime.now().astimezone()
        now_ts = start.timestamp()
        window = start - _dt.timedelta(days=1)             # 1 día atrás: capta eventos largos/en curso
        end = start + _dt.timedelta(days=21)
        async with aiohttp.ClientSession() as s:
            raws = await asyncio.gather(*[_fetch_ics(s, u) for u in CAL_URLS],
                                        return_exceptions=True)
        out, seen = [], set()
        for ci, raw in enumerate(raws):
            if isinstance(raw, Exception):
                import sys; print(f"[hud] cal {ci} fetch: {raw}", file=sys.stderr)
                continue
            try:
                cal = icalendar.Calendar.from_ical(raw)
                for e in recurring_ical_events.of(cal).between(window, end):
                    dt = e.get("DTSTART").dt
                    dtend = e.get("DTEND")
                    summ = str(e.get("SUMMARY", "(sin título)")).strip()
                    all_day = not isinstance(dt, _dt.datetime)
                    if all_day:
                        sdt = _dt.datetime.combine(dt, _dt.time(0, 0)).astimezone()
                        edt = (_dt.datetime.combine(dtend.dt, _dt.time(0, 0)).astimezone()
                               if dtend is not None else sdt + _dt.timedelta(days=1))
                    else:
                        sdt = dt.astimezone()
                        if dtend is not None and isinstance(dtend.dt, _dt.datetime):
                            edt = dtend.dt.astimezone()
                        else:
                            edt = sdt + _dt.timedelta(hours=1)   # sin fin: asume 1h
                    start_ts, end_ts = sdt.timestamp(), edt.timestamp()
                    if end_ts <= now_ts:                  # ya terminó -> fuera
                        continue
                    k = (round(start_ts), summ)
                    if k in seen:                         # mismo evento en 2 calendarios
                        continue
                    seen.add(k)
                    out.append({"start": start_ts, "end": end_ts, "summary": summ[:64],
                                "all_day": all_day, "cal": ci,
                                "in_progress": start_ts <= now_ts < end_ts})
            except Exception as ex:
                import sys; print(f"[hud] cal {ci} parse: {ex}", file=sys.stderr)
        out.sort(key=lambda x: x["start"])
        data = out[:8]
        _CAL.update(ts=now, data=data)
        return data
    except Exception as e:
        import sys
        print(f"[hud] calendario falló: {e}", file=sys.stderr)
        return _CAL["data"]


_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _evento_cuando(start_ts: float, all_day: bool, in_progress: bool) -> str:
    """Texto natural en español del momento de un evento (para el asistente de voz)."""
    if in_progress:
        return "ahora mismo, en curso"
    n = _dt.datetime.now()
    d = _dt.datetime.fromtimestamp(start_ts)            # hora local del contenedor (Madrid)
    diff = (d.date() - n.date()).days
    if diff == 0:
        dia = "hoy"
    elif diff == 1:
        dia = "mañana"
    elif diff == 2:
        dia = "pasado mañana"
    elif 3 <= diff <= 6:
        dia = f"el {_DIAS[d.weekday()]}"
    else:
        dia = f"el {d.day} de {_MESES[d.month - 1]}"
    return f"{dia}, todo el día" if all_day else f"{dia} a las {d.strftime('%H:%M')}"


def _llm_usage_today() -> dict:
    """Consumo de tokens del LLM (OpenCode Go) hoy, con coste estimado (precios GLM-5)."""
    out = {"tokens": 0, "prompt": 0, "completion": 0, "cache": 0, "requests": 0, "cost": 0.0}
    if not EVENTS_DB.exists():
        return out
    n = time.localtime()
    midnight = time.mktime((n.tm_year, n.tm_mon, n.tm_mday, 0, 0, 0, 0, 0, -1))
    conn = sqlite3.connect(EVENTS_DB)
    try:
        rows = conn.execute("SELECT payload FROM events WHERE ts>=? AND kind='llm_usage'",
                            (midnight,)).fetchall()
    finally:
        conn.close()
    for (pl,) in rows:
        try:
            d = json.loads(pl)
        except Exception:
            continue
        out["prompt"] += int(d.get("prompt", 0))
        out["completion"] += int(d.get("completion", 0))
        out["cache"] += int(d.get("cache", 0))
        out["requests"] += 1
    out["tokens"] = out["prompt"] + out["completion"]
    # GLM-5: $1.00/1M entrada, $3.20/1M salida, $0.20/1M lectura en caché
    fresh_in = max(0, out["prompt"] - out["cache"])
    out["cost"] = round(fresh_in * 1.0e-6 + out["cache"] * 0.2e-6 + out["completion"] * 3.2e-6, 4)
    return out


def _host_uptime() -> int | None:
    try:
        return int(float(Path("/proc/uptime").read_text().split()[0]))
    except Exception:
        return None


_CONTAINERS = {"ts": 0.0, "data": None}


async def _cached_containers() -> list:
    """Lista de contenedores cacheada ~5s: el HUD sondea cada 700ms y la lista
    cambia rara vez; evita martillear el socket-proxy de Docker en cada poll."""
    now = time.time()
    if _CONTAINERS["data"] is not None and (now - _CONTAINERS["ts"]) < 5:
        return _CONTAINERS["data"]
    data = await docker_client.list_containers()
    _CONTAINERS.update(ts=now, data=data)
    return data


# Versión del HUD (mtime de la plantilla): el kiosko se autorrecarga cuando cambia.
def _hud_version() -> int:
    try:
        return int(os.path.getmtime("templates/hud.html"))
    except Exception:
        return 0


async def _live_context() -> dict:
    containers = await _cached_containers()
    up = sum(1 for c in containers if c["state"] == "running")
    return {
        "containers": containers,
        "overview": {"up": up, "total": len(containers)},
        "metrics": _host_metrics(),
        "events": _recent_events(),
        "now": time.strftime("%H:%M:%S"),
    }


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/favicon.ico")
async def favicon():
    # SVG inline (sin fichero): cuadrado azul con "J"
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
           '<rect width="32" height="32" rx="6" fill="#1f6feb"/>'
           '<text x="16" y="22" font-size="18" fill="#fff" text-anchor="middle" '
           'font-family="sans-serif" font-weight="700">J</text></svg>')
    return Response(svg, media_type="image/svg+xml")


PROPS_FILE = Path("/logs/propuestas.json")
REVS_FILE = Path("/logs/config_revisions.json")   # revisiones del perfil (para rollback)


def _propuestas_pendientes() -> list:
    try:
        return [p for p in json.loads(PROPS_FILE.read_text(encoding="utf-8"))
                if p.get("estado") == "pendiente"]
    except Exception:
        return []


def _load_props() -> list:
    try:
        return json.loads(PROPS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_props(props: list) -> None:
    try:
        tmp = PROPS_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, PROPS_FILE)
    except Exception:
        pass


# --- revisiones del perfil con rollback (robado de Paperclip agent_config_revisions) ---
def _load_revs() -> list:
    try:
        return json.loads(REVS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_revs(revs: list) -> None:
    try:
        tmp = REVS_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(revs, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, REVS_FILE)
    except Exception:
        pass


def _record_revision(target: str, source: str, changed: str, before: str, after: str) -> None:
    revs = _load_revs()
    revs.append({"id": str(int(time.time() * 1000)), "target": target, "source": source,
                 "changed": changed, "before": before, "after": after, "ts": time.time()})
    _save_revs(revs[-50:])


def _recent_revisions(n: int = 6) -> list:
    """Últimas revisiones del perfil, para ofrecer 'deshacer' en el panel."""
    revs = [r for r in _load_revs() if r.get("target") == "perfil_usuario.md"]
    out = []
    for r in reversed(revs[-30:]):
        out.append({"id": r["id"], "changed": (r.get("changed") or "")[:90],
                    "time": time.strftime("%d %b %H:%M", time.localtime(r.get("ts", 0)))})
        if len(out) >= n:
            break
    return out


# --- audit log inmutable (robado de Paperclip activity_log) ---
def _audit(actor: str, action: str, entity_type: str, entity_id: str, details: dict | None = None) -> None:
    try:
        conn = sqlite3.connect(EVENTS_DB)
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                         " ts REAL, actor TEXT, action TEXT, entity_type TEXT, entity_id TEXT, details TEXT)")
            conn.execute("CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log "
                         "BEGIN SELECT RAISE(ABORT, 'audit_log es inmutable'); END")
            conn.execute("CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log "
                         "BEGIN SELECT RAISE(ABORT, 'audit_log es inmutable'); END")
            conn.execute("INSERT INTO audit_log(ts, actor, action, entity_type, entity_id, details)"
                         " VALUES (?,?,?,?,?,?)",
                         (time.time(), actor, action, entity_type, entity_id,
                          json.dumps(details or {}, ensure_ascii=False)))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def _events_authorized(request: Request) -> bool:
    if not EVENTS_SECRET:
        return False
    return hmac.compare_digest(request.headers.get("X-Jarvis-Events-Secret", ""), EVENTS_SECRET)


def _apply_decision(pid: str, accion: str, actor: str = "jose") -> dict:
    """Aplica una decisión sobre una propuesta (única fuente de verdad para panel y Telegram).
    aprobar -> revisión + append al perfil + audit; rechazar/reformular -> estado + audit."""
    props = _load_props()
    target = next((p for p in props if p.get("id") == pid and p.get("estado") == "pendiente"), None)
    if not target:
        return {"status": "error", "mensaje": "propuesta no encontrada o ya resuelta"}
    if accion == "aprobar":
        perfil = PERSONA_DIR / "perfil_usuario.md"
        try:
            before = perfil.read_text(encoding="utf-8") if perfil.exists() else "# Perfil de José (evolutivo)\n"
            after = before.rstrip() + "\n- " + target.get("aplicar", "") + "\n"
            perfil.write_text(after, encoding="utf-8")
        except Exception as e:
            return {"status": "error", "mensaje": str(e)}
        _record_revision("perfil_usuario.md", f"proposal:{pid}", target.get("aplicar", ""), before, after)
        target["estado"] = "aprobada"
        _audit(actor, "proposal.approved", "proposal", pid, {"aplicar": target.get("aplicar", "")})
    elif accion == "rechazar":
        target["estado"] = "rechazada"
        _audit(actor, "proposal.rejected", "proposal", pid, {"aplicar": target.get("aplicar", "")})
    elif accion == "reformular":
        target["estado"] = "revision_requested"
        _audit(actor, "proposal.revision_requested", "proposal", pid, {"aplicar": target.get("aplicar", "")})
    else:
        return {"status": "error", "mensaje": "acción inválida"}
    _save_props(props)
    return {"status": "ok", "estado": target["estado"]}


@app.post("/propuesta/{pid}")
async def propuesta_accion(pid: str, accion: str = Form(...), password: str = Form("")):
    """Aprobar/rechazar/reformular desde el panel web (segundo factor: contraseña)."""
    if not _check_password(password):
        return HTMLResponse("Contraseña incorrecta", status_code=403)
    _apply_decision(pid, accion, actor="jose")
    return RedirectResponse("/", status_code=303)


@app.post("/api/propuesta/decision")
async def propuesta_decision(request: Request):
    """Endpoint interno (lo llama el agente de Telegram). Auth por EVENTS_SECRET."""
    if not _events_authorized(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    data = await request.json()
    res = _apply_decision((data.get("pid") or "").strip(), (data.get("accion") or "").strip(),
                          actor="telegram")
    return JSONResponse(res, status_code=200 if res.get("status") == "ok" else 400)


@app.post("/propuesta/rollback/{rev_id}")
async def propuesta_rollback(rev_id: str, password: str = Form("")):
    """Deshace un cambio del perfil reaplicando el snapshot 'before' de una revisión."""
    if not _check_password(password):
        return HTMLResponse("Contraseña incorrecta", status_code=403)
    rev = next((r for r in _load_revs()
                if r.get("id") == rev_id and r.get("target") == "perfil_usuario.md"), None)
    if rev:
        perfil = PERSONA_DIR / "perfil_usuario.md"
        try:
            cur = perfil.read_text(encoding="utf-8") if perfil.exists() else ""
            perfil.write_text(rev["before"], encoding="utf-8")
            _record_revision("perfil_usuario.md", f"rollback:{rev_id}", "(deshacer)", cur, rev["before"])
            _audit("jose", "profile.config_rolled_back", "revision", rev_id, {})
        except Exception:
            pass
    return RedirectResponse("/", status_code=303)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    ctx = await _live_context()
    ctx.update({"request": request, "user": request.state.user,
                "personas": _personas(), "propuestas": _propuestas_pendientes(),
                "revisiones": _recent_revisions(),
                "tools": yaml.safe_load(TOOLS_YAML.read_text(encoding="utf-8")).get("tools", {})})
    # Starlette >=0.29: request va primero (firma nueva)
    return templates.TemplateResponse(request, "index.html", ctx)


@app.get("/partials/live", response_class=HTMLResponse)
async def partial_live(request: Request):
    """Fragmento HTML (métricas + servicios + eventos) que htmx refresca cada pocos segundos."""
    return templates.TemplateResponse(request, "_live.html", await _live_context())


@app.get("/hud", response_class=HTMLResponse)
async def hud(request: Request):
    """Pantalla kiosko a tiempo real (monitor del homelab). Sin login, solo lectura."""
    return templates.TemplateResponse(request, "hud.html", {"request": request})


@app.get("/api/hud")
async def api_hud():
    """Datos en JSON para el HUD: servicios, métricas, interacciones, estado de voz."""
    ctx = await _live_context()
    # Servicios opcionales/por-perfil que pueden estar parados a propósito (no son fallo):
    # stt-parakeet (no se usa, va Whisper), vision (Fase 5 desactivada), reflection (job 04:00).
    OPTIONAL_SVC = {"stt-parakeet", "vision", "reflection"}
    services = []
    for c in ctx["containers"]:
        nm = c["name"].replace("jarvis-", "").rsplit("-", 1)[0]
        services.append({"name": nm, "running": c["state"] == "running", "optional": nm in OPTIONAL_SVC})
    interactions = []
    for e in ctx["events"]:
        k = e["kind"]
        if k in ("user_said", "assistant_said"):
            try:
                text = (json.loads(e["payload"]) or {}).get("text", "").strip()
            except Exception:
                text = (e["payload"] or "").strip()
            if not text:
                continue
            # No ensuciar el feed con fugas de tool-calls (p.ej. '<web_search>{...}')
            if k == "assistant_said" and text[:1] in ("<", "{", "["):
                continue
            interactions.append({"ts": e["ts"], "time": e["time"], "role": "jarvis" if k == "assistant_said" else "user", "text": text})
        elif k == "presence":
            interactions.append({"ts": e["ts"], "time": e["time"], "role": "sys", "text": "Presencia detectada en casa"})
    # Estado de voz EN VIVO (no derivado del último evento): mata el "RESPONDIENDO" pegado.
    voice = _voice_state()
    if voice.get("fresh") and not voice["sub"] and interactions:
        voice["sub"] = interactions[0]["text"][:80]
    # Salud "real": solo cuenta los servicios NO opcionales (evita alerta roja perpetua).
    core = [s for s in services if not s["optional"]]
    ov = {"up": sum(1 for s in core if s["running"]), "total": len(core)}
    healthy = all(s["running"] for s in core)
    tele = _voice_telemetry()
    return {
        "now": ctx["now"], "metrics": ctx["metrics"], "overview": ov, "services": services,
        "interactions": interactions, "voice": voice, "healthy": healthy,
        "server_epoch": time.time(),
        "version": _hud_version(),
        "weather": await _weather(),
        "agenda": await _calendar(),
        "usage": _llm_usage_today(),
        "briefing_active": _briefing_active(),
        "spotify": await _spotify(),
        "telemetry": {
            "host_uptime": _host_uptime(),
            "wakes_today": tele["wakes_today"],
            "convos_today": tele["convos_today"],
            "last_heard": tele["last_heard"],
            "model_stt": f"whisper {voice['model']}" if voice.get("model") else "whisper small",
            "model_llm": "GLM-5",
            "level": voice.get("level"),
            "voice_fresh": voice.get("fresh", False),
        },
    }


@app.get("/api/agenda")
async def api_agenda():
    """Agenda para el asistente de voz (la consulta el orquestador, sin login).
    Devuelve los próximos eventos con un 'cuando' ya legible en español."""
    evs = await _calendar()
    if evs is None:
        return {"configurado": False, "eventos": []}
    out = [{
        "cuando": _evento_cuando(e["start"], e["all_day"], e["in_progress"]),
        "titulo": e["summary"],
        "en_curso": e["in_progress"],
        "start": e["start"], "end": e["end"], "all_day": e["all_day"],
    } for e in evs]
    return {"configurado": True, "eventos": out}


def _reminders_today() -> list:
    try:
        rems = json.loads(Path("/logs/reminders.json").read_text(encoding="utf-8"))
    except Exception:
        return []
    today = time.strftime("%Y-%m-%d")
    out = []
    for r in rems:
        if r.get("done") or time.strftime("%Y-%m-%d", time.localtime(r.get("due", 0))) != today:
            continue
        out.append({"texto": r.get("texto", ""), "hora": time.strftime("%H:%M", time.localtime(r["due"]))})
    return out


def _briefing_active() -> bool:
    """El briefing se muestra en el HUD de 7 a 9, salvo que se haya descartado ('buenos días')."""
    if not (7 <= time.localtime().tm_hour < 9):
        return False
    try:
        st = json.loads(Path("/logs/briefing.json").read_text(encoding="utf-8"))
        if st.get("date") == time.strftime("%Y-%m-%d") and st.get("dismissed"):
            return False
    except Exception:
        pass
    return True


@app.get("/spotify/login")
async def spotify_login():
    """Inicio de la autorización de Spotify (una sola vez)."""
    if not SPOTIFY_ID:
        return HTMLResponse("Falta SPOTIFY_CLIENT_ID", status_code=500)
    scope = "user-read-currently-playing user-read-playback-state"
    url = ("https://accounts.spotify.com/authorize?response_type=code"
           f"&client_id={SPOTIFY_ID}&scope={_uparse.quote(scope)}"
           f"&redirect_uri={_uparse.quote(SPOTIFY_REDIRECT)}")
    return RedirectResponse(url)


@app.get("/spotify/callback", response_class=HTMLResponse)
async def spotify_callback(code: str = "", error: str = ""):
    if error or not code:
        return HTMLResponse(f"<h2>Autorización cancelada</h2><p>{error or 'sin code'}</p>", status_code=400)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post("https://accounts.spotify.com/api/token", data={
                "grant_type": "authorization_code", "code": code,
                "redirect_uri": SPOTIFY_REDIRECT,
                "client_id": SPOTIFY_ID, "client_secret": SPOTIFY_SECRET,
            }, timeout=aiohttp.ClientTimeout(total=10)) as r:
                j = await r.json()
    except Exception as e:
        return HTMLResponse(f"<h2>Error</h2><p>{e}</p>", status_code=500)
    refresh = j.get("refresh_token")
    if not refresh:
        return HTMLResponse(f"<h2>No llegó refresh_token</h2><pre>{j}</pre>", status_code=400)
    try:
        _SPOTIFY_REFRESH_FILE.write_text(refresh, encoding="utf-8")
    except Exception as e:
        return HTMLResponse(f"<h2>No pude guardar el token</h2><p>{e}</p>", status_code=500)
    return HTMLResponse("<h2 style='font-family:sans-serif'>Spotify conectado ✓</h2>"
                        "<p style='font-family:sans-serif'>Ya puedes cerrar esta pestaña. "
                        "El widget aparecerá en la pantalla cuando suene música.</p>")


@app.get("/api/briefing")
async def api_briefing():
    """Contenido del resumen del día (lo consume la tool briefing_matutino y el HUD)."""
    w = await _weather()
    evs = await _calendar() or []
    now, today = time.time(), time.strftime("%Y-%m-%d")
    hoy = [e for e in evs
           if time.strftime("%Y-%m-%d", time.localtime(e["start"])) == today and e["end"] > now]
    return {
        "weather": w,
        "eventos_hoy": [{"cuando": _evento_cuando(e["start"], e["all_day"], e["in_progress"]),
                         "titulo": e["summary"]} for e in hoy],
        "recordatorios": _reminders_today(),
    }


@app.get("/logs/{name}", response_class=HTMLResponse)
async def view_logs(request: Request, name: str):
    # Validar contra los contenedores reales (evita rutas arbitrarias al proxy).
    containers = await docker_client.list_containers()
    if name not in {c["name"] for c in containers}:
        return HTMLResponse("Contenedor desconocido", status_code=404)
    logs = await docker_client.get_logs(name, tail=300)
    return templates.TemplateResponse(request, "logs.html", {"name": name, "logs": logs})


@app.post("/persona/{key}")
async def save_persona(key: str, content: str = Form(...), password: str = Form("")):
    if not _check_password(password):
        return HTMLResponse("Contraseña incorrecta", status_code=403)
    if key not in PERSONA_FILES:
        return HTMLResponse("Fichero no permitido", status_code=400)
    (PERSONA_DIR / PERSONA_FILES[key][0]).write_text(content, encoding="utf-8")
    # El commit de git se hace en el host (el .git no se monta) — ver RUNBOOK.
    return RedirectResponse("/", status_code=303)


@app.post("/tools/toggle")
async def toggle_tool(name: str = Form(...), password: str = Form("")):
    if not _check_password(password):
        return HTMLResponse("Contraseña incorrecta", status_code=403)
    data = yaml.safe_load(TOOLS_YAML.read_text(encoding="utf-8"))
    if name in data.get("tools", {}):
        data["tools"][name]["enabled"] = not data["tools"][name].get("enabled", False)
        TOOLS_YAML.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    # v1: orchestrator reads tools.yaml at startup → restart it to apply.
    return RedirectResponse("/", status_code=303)


@app.post("/dnd")
async def toggle_dnd(enabled: str = Form(...), password: str = Form("")):
    if not _check_password(password):
        return HTMLResponse("Contraseña incorrecta", status_code=403)
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"{ORCHESTRATOR}/dnd",
                json={"enabled": enabled == "true"},
                headers={"X-Jarvis-Events-Secret": EVENTS_SECRET},
                timeout=aiohttp.ClientTimeout(total=5),
            )
    except Exception:
        # Orquestador caído (p. ej. voz apagada): no reventar el panel.
        return HTMLResponse(
            "<p>Orquestador no disponible (¿la voz está apagada?). DND no aplicado.</p>"
            "<p><a href='/'>← Volver</a></p>",
            status_code=200,
        )
    return RedirectResponse("/", status_code=303)
