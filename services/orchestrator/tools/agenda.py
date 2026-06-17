"""consultar_agenda — el asistente lee la agenda del usuario.

Los eventos los sirve el panel (que ya combina los calendarios ICS, expande
recurrencias y oculta lo pasado) en GET /api/agenda, con un 'cuando' legible.
Read-only, sin efectos: solo consulta y devuelve.
"""

import os

import aiohttp

PANEL = os.getenv("PANEL_INTERNAL", "http://panel:8080")


async def consultar_agenda(security=None) -> dict:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{PANEL}/api/agenda", timeout=aiohttp.ClientTimeout(total=8)) as r:
                r.raise_for_status()
                data = await r.json()
    except Exception as e:
        return {"status": "error", "mensaje": f"No he podido consultar el calendario: {e}"}

    if not data.get("configurado"):
        return {"status": "sin_calendario",
                "mensaje": "No hay ningún calendario configurado."}
    eventos = data.get("eventos", [])
    if not eventos:
        return {"eventos": [], "mensaje": "No hay eventos próximos en la agenda."}
    return {"eventos": [
        {"cuando": e["cuando"], "titulo": e["titulo"], "en_curso": e["en_curso"]}
        for e in eventos
    ]}
