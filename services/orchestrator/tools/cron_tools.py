"""Tools de tareas programadas (cron NL). José las crea/lista/cancela por voz o
Telegram; el bucle de cron.py las ejecuta. Son benignas (programar un aviso no tiene
efecto destructivo) -> read_only, sin confirmación."""

import time

import cron


async def programar_tarea(cuando: str, tarea: str, security=None) -> dict:
    sched = cron.parse_schedule(cuando)
    if not sched:
        return {"status": "error",
                "mensaje": ("No he entendido cada cuánto. Normalízalo como 'cada:30m', 'cada:2h', "
                            "'diario:08:00' o 'semanal:lun:09:00'.")}
    if not (tarea or "").strip():
        return {"status": "error", "mensaje": "¿Qué tarea quiere que programe, señor?"}
    jobs = cron.load()
    jobs.append({"id": str(int(time.time() * 1000)), "tarea": tarea.strip(), "sched": sched,
                 "enabled": True, "next": cron.compute_next(sched, time.time())})
    cron.save(jobs)
    return {"status": "ok", "mensaje": f"Anotado, señor: {cron.describe(sched)}, {tarea.strip()}."}


async def listar_tareas(security=None) -> dict:
    jobs = [j for j in cron.load() if j.get("enabled", True)]
    if not jobs:
        return {"tareas": [], "mensaje": "No tiene ninguna tarea programada, señor."}
    return {"tareas": [{"que": j["tarea"], "cuando": cron.describe(j.get("sched"))} for j in jobs]}


async def cancelar_tarea(cual: str, security=None) -> dict:
    q = (cual or "").strip().lower()
    if not q:
        return {"status": "error", "mensaje": "¿Cuál quiere cancelar, señor?"}
    jobs = cron.load()
    matches = [j for j in jobs if q in j.get("tarea", "").lower()]
    if not matches:
        return {"status": "error", "mensaje": "No encuentro esa tarea programada, señor."}
    if len(matches) > 1:
        return {"status": "varias",
                "mensaje": "Hay varias que encajan: " + "; ".join(j["tarea"] for j in matches) + ". Sea más concreto."}
    keep = [j for j in jobs if j is not matches[0]]
    cron.save(keep)
    return {"status": "ok", "mensaje": f"Cancelada, señor: {matches[0]['tarea']}."}
