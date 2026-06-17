"""encargar — Jarvis delega una TAREA REAL (acciones) a Claude Code en el host.

A diferencia de `investigar` (solo lectura/web), aquí Claude Code puede crear/editar
archivos y EJECUTAR comandos en el homelab COMO jose (sin sudo/root). Por eso la
tool es `side_effect`: el registro de tools (voz y texto) la fuerza a pasar por
CONFIRMACIÓN explícita antes de ejecutarse. Es asíncrona: arranca y avisa al
terminar por /event/say (que enruta a voz o Telegram según presencia).
"""

import os
import time

import aiohttp

from audit import audit

BRIDGE = os.getenv("RESEARCH_BRIDGE", "http://host.docker.internal:8077")


async def encargar(tarea: str, security=None) -> dict:
    tarea = (tarea or "").strip()
    if not tarea:
        return {"status": "error", "mensaje": "¿Qué quiere que haga, señor?"}
    rid = str(int(time.time()))                    # correlaciona audit_log <-> log de acción del puente
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{BRIDGE}/do",
                json={"tarea": tarea, "id": rid},
                headers={"X-Jarvis-Events-Secret": os.getenv("EVENTS_SECRET", "")},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 202:
                    audit("jarvis", "action.delegated", "encargar", rid, {"tarea": tarea[:300]})
                    return {"status": "en_marcha",
                            "mensaje": f"De acuerdo, señor. Me pongo con ello: {tarea}. Le aviso al terminar."}
                if r.status == 403:
                    return {"status": "error",
                            "mensaje": "Las acciones están desactivadas ahora mismo, señor."}
                return {"status": "error",
                        "mensaje": "No he podido poner en marcha la tarea, señor."}
    except Exception:
        return {"status": "error",
                "mensaje": "Mi operador no responde ahora mismo, señor."}
