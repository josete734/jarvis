"""Cliente del puente jarvis-research para el control de pantalla (Descansa/Revive).

Espejo de `tools/encargar.py`: mismo BRIDGE y header de secreto. El host expone
`POST /power {action: sleep|wake}` (síncrono) que apaga/enciende el kiosko del HUD.
No lanza excepciones: degrada con log y devuelve False si el puente no responde.
"""

import os

import aiohttp
from loguru import logger

BRIDGE = os.getenv("RESEARCH_BRIDGE", "http://host.docker.internal:8077")


async def screen(action: str) -> bool:
    """Pide al host apagar (sleep) o encender (wake) la pantalla del HUD."""
    if action not in ("sleep", "wake"):
        return False
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{BRIDGE}/power",
                json={"action": action},
                headers={"X-Jarvis-Events-Secret": os.getenv("EVENTS_SECRET", "")},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                if r.status != 200:
                    logger.warning(f"[power] /power {action} -> HTTP {r.status}")
                    return False
                return True
    except Exception as e:
        logger.warning(f"[power] puente no responde: {e}")
        return False
