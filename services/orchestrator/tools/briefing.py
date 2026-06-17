"""briefing_matutino — resumen del día (clima + agenda de hoy + recordatorios) para
que Jarvis lo lea, p.ej. cuando José dice «buenos días». Marca el briefing como
visto para que desaparezca de la pantalla."""

import json
import os
import time
from pathlib import Path

import aiohttp

PANEL = os.getenv("PANEL_INTERNAL", "http://panel:8080")
STATE = Path("/logs/briefing.json")


def _dismiss() -> None:
    try:
        STATE.write_text(json.dumps({"date": time.strftime("%Y-%m-%d"), "dismissed": True}),
                         encoding="utf-8")
    except Exception:
        pass


async def briefing_matutino(security=None) -> dict:
    _dismiss()                                   # lo quita de la pantalla
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{PANEL}/api/briefing",
                             timeout=aiohttp.ClientTimeout(total=8)) as r:
                d = await r.json()
    except Exception:
        return {"status": "error", "mensaje": "No he podido reunir el resumen del día, señor."}
    return {
        "saludo": "buenos días",
        "tiempo": d.get("weather"),
        "eventos_hoy": d.get("eventos_hoy", []),
        "recordatorios": d.get("recordatorios", []),
    }
