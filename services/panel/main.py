"""Control panel — FastAPI + HTMX (PLAN_FINAL §9.2, Fase 6).

Auth: el contenedor escucha en 127.0.0.1 y solo lo alcanzan dos caminos que
inyectan identidad — `tailscale serve` (tailnet) o Cloudflare Tunnel + Access
(internet). El middleware exige email ∈ PANEL_ALLOWED_USERS (fail-closed).
PANEL_PASSWORD es segundo factor para acciones mutantes (persona, tools, DND).

Funciones: estado de servicios + métricas del host (en vivo, htmx), eventos,
editor de las personas, toggle de tools y de "no molestar".
Pendiente: dashboard de latencias por etapa (depende de la voz).
"""

import os
import sqlite3
import time
from pathlib import Path

import aiohttp
import yaml
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
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

app = FastAPI(title="jarvis-panel")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.middleware("http")
async def identity(request: Request, call_next):
    if request.url.path in ("/health", "/favicon.ico"):
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
            f"<h1>403</h1><p>Identidad no autorizada: {user or '(sin header)'}.</p>"
            "<p>Entra por el tailnet (<code>tailscale serve</code>) o por "
            "<code>jarvis.calahierbas.casa</code> (Cloudflare Access).</p>",
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


async def _live_context() -> dict:
    containers = await docker_client.list_containers()
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


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    ctx = await _live_context()
    ctx.update({"request": request, "user": request.state.user,
                "personas": _personas(),
                "tools": yaml.safe_load(TOOLS_YAML.read_text(encoding="utf-8")).get("tools", {})})
    # Starlette >=0.29: request va primero (firma nueva)
    return templates.TemplateResponse(request, "index.html", ctx)


@app.get("/partials/live", response_class=HTMLResponse)
async def partial_live(request: Request):
    """Fragmento HTML (métricas + servicios + eventos) que htmx refresca cada pocos segundos."""
    return templates.TemplateResponse(request, "_live.html", await _live_context())


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
