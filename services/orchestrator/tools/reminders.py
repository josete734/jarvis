"""crear_recordatorio — guarda un recordatorio que el heartbeat dirá por voz a su
hora. El LLM pasa 'cuando' ya en ISO (tiene el momento actual inyectado)."""

import datetime as dt

from proactive import add_reminder

_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d")


def _parse(cuando: str):
    cuando = (cuando or "").strip().replace("Z", "")
    for fmt in _FORMATS:
        try:
            return dt.datetime.strptime(cuando, fmt).timestamp()
        except ValueError:
            continue
    return None


async def crear_recordatorio(texto: str, cuando: str = "", security=None) -> dict:
    texto = (texto or "").strip()
    if not texto:
        return {"status": "error", "mensaje": "¿Qué quiere que le recuerde, señor?"}
    due = _parse(cuando)
    if due is None:
        return {"status": "falta_hora", "mensaje": "¿Para cuándo se lo recuerdo, señor?"}
    add_reminder(texto, due)
    return {"status": "ok", "mensaje": "Anotado, señor."}
