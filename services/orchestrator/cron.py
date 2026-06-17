"""Cron en lenguaje natural (Bloque 3) — tareas programadas que corren un PROMPT
de Jarvis con sus herramientas y avisan por el gate (voz/Telegram según presencia)
SOLO si hay algo que decir (patrón [SILENT] de Hermes).

SEGURIDAD: NO ejecuta scripts arbitrarios. Cada tarea es un prompt que el LLM
resuelve con sus tools ya sandboxed (web_search, consultar_agenda, recordar…). Así
hay "monitores" ("cada hora mira si hay algo urgente en la agenda") sin abrir una vía
de ejecución de comandos.

Horario normalizado (lo pasa el LLM al programar, vía la tool programar_tarea):
  cada:<N><m|h|d>      -> intervalo (cada:30m, cada:2h)
  diario:HH:MM         -> todos los días a esa hora (hora de España)
  semanal:<dow>:HH:MM  -> dow ∈ lun,mar,mie,jue,vie,sab,dom
"""

import asyncio
import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp
from loguru import logger

import sysprompt
from security_core import SecurityState

CRON = Path("/logs/cron.json")
LLM = os.getenv("LLM_BASE", "http://litellm:4000/v1")
LLM_KEY = os.getenv("LITELLM_API_KEY", "sk-litellm")
SILENT = "[SILENT]"
MAX_TOOL_ITERS = 4

_UNIT = {"m": 60, "h": 3600, "d": 86400}
_DOW = {"lun": 0, "mar": 1, "mie": 2, "mié": 2, "jue": 3, "vie": 4, "sab": 5, "sáb": 5, "dom": 6}
_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre"]


def _momento() -> str:
    n = datetime.now()
    return (f"\n\n## Momento actual (dato del sistema)\nAhora es {_DIAS[n.weekday()]} {n.day} de "
            f"{_MESES[n.month - 1]} de {n.year}, las {n.hour:02d}:{n.minute:02d} (hora de España).")


# --- store (compartido con las tools) --------------------------------------
def load() -> list:
    try:
        return json.loads(CRON.read_text(encoding="utf-8"))
    except Exception:
        return []


def save(jobs: list) -> None:
    try:
        tmp = CRON.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, CRON)
    except Exception as e:
        logger.warning(f"cron save: {e}")


def parse_schedule(cuando: str) -> dict | None:
    c = (cuando or "").strip().lower()
    m = re.fullmatch(r"cada:(\d+)\s*([mhd])", c)
    if m:
        return {"kind": "interval", "secs": int(m.group(1)) * _UNIT[m.group(2)]}
    m = re.fullmatch(r"diario:(\d{1,2}):(\d{2})", c)
    if m:
        return {"kind": "daily", "hh": int(m.group(1)), "mm": int(m.group(2))}
    m = re.fullmatch(r"semanal:([a-zé]{3}):(\d{1,2}):(\d{2})", c)
    if m and m.group(1) in _DOW:
        return {"kind": "weekly", "dow": _DOW[m.group(1)], "hh": int(m.group(2)), "mm": int(m.group(3))}
    # Fallback en lenguaje natural (por si el LLM no normaliza el formato)
    if "cada hora" in c:
        return {"kind": "interval", "secs": 3600}
    m = re.search(r"cada\s+(\d+)\s*(min|minuto|h|hora)", c)
    if m:
        return {"kind": "interval", "secs": int(m.group(1)) * (3600 if m.group(2).startswith("h") else 60)}
    m = re.search(r"(?:cada d[ií]a|todos los d[ií]as|a diario)\D*(\d{1,2})(?::(\d{2}))?", c)
    if m:
        return {"kind": "daily", "hh": int(m.group(1)), "mm": int(m.group(2) or 0)}
    m = re.search(r"cada\s+(lun|mar|mi[eé]|jue|vie|s[áa]b|dom)\w*\D*(\d{1,2})(?::(\d{2}))?", c)
    if m and m.group(1) in _DOW:
        return {"kind": "weekly", "dow": _DOW[m.group(1)], "hh": int(m.group(2)), "mm": int(m.group(3) or 0)}
    return None


def compute_next(sched: dict, from_ts: float) -> float:
    if sched["kind"] == "interval":
        return from_ts + max(60, sched["secs"])
    base = datetime.fromtimestamp(from_ts)
    nxt = base.replace(hour=sched["hh"], minute=sched["mm"], second=0, microsecond=0)
    if sched["kind"] == "daily":
        if nxt.timestamp() <= from_ts:
            nxt += timedelta(days=1)
        return nxt.timestamp()
    # weekly
    days = (sched["dow"] - nxt.weekday()) % 7
    nxt += timedelta(days=days)
    if nxt.timestamp() <= from_ts:
        nxt += timedelta(days=7)
    return nxt.timestamp()


def describe(sched: dict) -> str:
    if not sched:
        return "?"
    if sched["kind"] == "interval":
        s = sched["secs"]
        return f"cada {s // 3600} h" if s >= 3600 else f"cada {s // 60} min"
    if sched["kind"] == "daily":
        return f"cada día a las {sched['hh']:02d}:{sched['mm']:02d}"
    rev = {v: k for k, v in _DOW.items()}
    return f"cada {rev.get(sched['dow'], '?')} a las {sched['hh']:02d}:{sched['mm']:02d}"


# --- runner ----------------------------------------------------------------
async def _chat(messages: list, tools: list) -> dict:
    body = {"model": "jarvis-main", "messages": messages, "tools": tools,
            "max_tokens": 300, "extra_body": {"reasoning_effort": "none"}}
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{LLM}/chat/completions", json=body,
                          headers={"Authorization": "Bearer " + LLM_KEY},
                          timeout=aiohttp.ClientTimeout(total=90)) as r:
            return await r.json()


class Cron:
    """Bucle que revisa las tareas y dispara las vencidas por el gate proactivo."""

    def __init__(self, gate):
        self._gate = gate
        self._sec = SecurityState()

    async def _run_job(self, job: dict) -> None:
        from tools.registry import dispatch, tool_specs   # perezoso: evita import circular
        instr = (
            f"Es una TAREA PROGRAMADA recurrente: «{job['tarea']}». Resuélvela AHORA con tus "
            f"herramientas si hace falta, y decide:\n"
            f"- Si la tarea es DARLE o INFORMARLE de algo (un parte, el tiempo, un resumen, un "
            f"recordatorio): dáselo en 1-2 frases de mayordomo, SIEMPRE.\n"
            f"- Si la tarea es VIGILAR y avisar SOLO si pasa algo, y ahora mismo NO pasa nada "
            f"relevante: responde EXACTAMENTE {SILENT} y nada más.\n"
            f"No saludes ni expliques la tarea; ve al grano.")
        messages = [{"role": "system", "content": sysprompt.compose("voz") + _momento()},
                    {"role": "user", "content": instr}]
        specs = tool_specs()
        final = None
        for _ in range(MAX_TOOL_ITERS):
            try:
                j = await _chat(messages, specs)
                msg = j["choices"][0]["message"]
            except Exception as e:
                logger.warning(f"[cron] job {job.get('id')} LLM: {e}")
                return
            tcs = msg.get("tool_calls")
            if not tcs:
                final = (msg.get("content") or "").strip()
                break
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tcs})
            for tc in tcs:
                fn = (tc.get("function") or {}).get("name", "")
                try:
                    args = json.loads((tc["function"].get("arguments") or "{}"))
                except Exception:
                    args = {}
                res = await dispatch(fn, args, self._sec)
                content = json.dumps(res, ensure_ascii=False)
                if len(content) > 4000:
                    content = content[:4000] + "…(recortado)"
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": content})
        if not final or SILENT in final.upper():
            logger.info(f"[cron] job {job.get('id')} -> silencio")
            return
        await self._gate.say(final, key=f"cron:{job['id']}", tier="info")

    async def run(self) -> None:
        await asyncio.sleep(45)
        logger.info("[cron] en marcha")
        while True:
            try:
                jobs = load()
                now = time.time()
                changed = False
                for job in jobs:
                    if not job.get("enabled", True):
                        continue
                    sched = job.get("sched")
                    if not sched:
                        continue
                    if "next" not in job:
                        job["next"] = compute_next(sched, now)
                        changed = True
                    if job["next"] <= now:
                        await self._run_job(job)
                        job["last"] = now
                        job["next"] = compute_next(sched, now)
                        changed = True
                if changed:
                    save(jobs)
            except Exception as e:
                logger.warning(f"[cron] tick: {e}")
            await asyncio.sleep(30)
