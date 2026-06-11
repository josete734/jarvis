"""Control panel — FastAPI + HTMX (PLAN_FINAL §9.2, Fase 6).

Auth model: the container binds to 127.0.0.1 on the host and is ONLY reachable
through `tailscale serve`, which injects identity headers for tailnet traffic.
The middleware below requires Tailscale-User-Login ∈ PANEL_ALLOWED_USERS.
PANEL_PASSWORD is a second factor for mutating actions (persona, tools, DND).

v1 scope: service status (via docker-socket-proxy), recent events, persona
editor (file save; git commit happens host-side — see RUNBOOK), tools toggle,
DND switch. Latency dashboards: TODO(Fase 6).
"""

import json
import os
import sqlite3
import time
from pathlib import Path

import aiohttp
import yaml
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import docker_client

ALLOWED = {u.strip() for u in os.getenv("PANEL_ALLOWED_USERS", "").split(",") if u.strip()}
PASSWORD = os.getenv("PANEL_PASSWORD", "")
PERSONA = Path("/persona/jarvis.md")
TOOLS_YAML = Path("/config/tools.yaml")
EVENTS_DB = Path("/logs/events.db")
ORCHESTRATOR = os.getenv("ORCHESTRATOR_EVENTS", "http://orchestrator:8070")
EVENTS_SECRET = os.getenv("EVENTS_SECRET", "")

app = FastAPI(title="jarvis-panel")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.middleware("http")
async def tailscale_identity(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)
    user = request.headers.get("Tailscale-User-Login", "")
    # Fail-closed: sin allowlist configurada (PANEL_ALLOWED_USERS vacío) se deniega todo.
    if not ALLOWED or user not in ALLOWED:
        return HTMLResponse(
            f"<h1>403</h1><p>Identidad de Tailscale no autorizada: {user or '(sin header)'}.</p>"
            "<p>Accede vía <code>tailscale serve</code> desde el tailnet.</p>",
            status_code=403,
        )
    request.state.user = user
    return await call_next(request)


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
        {"time": time.strftime("%d %b %H:%M:%S", time.localtime(ts)), "kind": k, "payload": p}
        for ts, k, p in rows
    ]


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": request.state.user,
            "containers": await docker_client.list_containers(),
            "events": _recent_events(),
            "persona": PERSONA.read_text(encoding="utf-8") if PERSONA.exists() else "",
            "tools": yaml.safe_load(TOOLS_YAML.read_text(encoding="utf-8")).get("tools", {}),
        },
    )


@app.post("/persona")
async def save_persona(content: str = Form(...), password: str = Form("")):
    if not _check_password(password):
        return HTMLResponse("Contraseña incorrecta", status_code=403)
    PERSONA.write_text(content, encoding="utf-8")
    # Git commit is done host-side (repo .git is not mounted) — see RUNBOOK.
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
    async with aiohttp.ClientSession() as session:
        await session.post(
            f"{ORCHESTRATOR}/dnd",
            json={"enabled": enabled == "true"},
            headers={"X-Jarvis-Events-Secret": EVENTS_SECRET},
        )
    return RedirectResponse("/", status_code=303)
