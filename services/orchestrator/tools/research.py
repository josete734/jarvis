"""investigar — Jarvis (Mycroth) delega una investigación profunda a Claude Code.

El trabajo pesado lo hace `claude -p` en el host (puente jarvis-research, con los
TOKENS de Claude del usuario y herramientas de lectura/web). Es ASÍNCRONO: arranca
y devuelve al instante; Jarvis avisa por voz cuando termina (vía /event/say).
"""

import os

import aiohttp

BRIDGE = os.getenv("RESEARCH_BRIDGE", "http://host.docker.internal:8077")


async def investigar(tema: str, security=None) -> dict:
    tema = (tema or "").strip()
    if not tema:
        return {"status": "error", "mensaje": "¿Sobre qué quiere que investigue, señor?"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{BRIDGE}/research",
                json={"tema": tema},
                headers={"X-Jarvis-Events-Secret": os.getenv("EVENTS_SECRET", "")},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 202:
                    return {"status": "en_marcha",
                            "mensaje": f"Me pongo a investigar «{tema}». Le aviso en cuanto lo tenga."}
                return {"status": "error",
                        "mensaje": "No he podido poner en marcha la investigación, señor."}
    except Exception:
        return {"status": "error",
                "mensaje": "Mi equipo de investigación no responde ahora mismo, señor."}
