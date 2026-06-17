"""Curator de memoria — Jarvis aprende solo de las conversaciones (patrón Hermes).

Cada cierto rato revisa los turnos nuevos de events.db y extrae con el LLM (GLM-5,
barato) los HECHOS DURABLES sobre José que merezca recordar, y los fusiona en
/logs/aprendido.md (que el bot carga en el system prompt). Son DATOS (gustos,
personas, rutinas), no comportamiento: se auto-escriben sin pedir permiso. La
auto-mejora de PERSONA/tono sí irá por aprobación (otra pieza).
"""

import asyncio
import datetime as _dt
import json
import os
import re
import shutil
import sqlite3
import time
from pathlib import Path

import aiohttp
from loguru import logger

DB = Path("/logs/events.db")
FACTS = Path("/logs/aprendido.md")
STATE = Path("/logs/curator_state.json")
PROPS = Path("/logs/propuestas.json")
PROPOSE_EVERY = int(os.getenv("CURATOR_PROPOSE_EVERY", "6"))   # propone mejoras cada ~6 ciclos
MAX_PENDING = int(os.getenv("CURATOR_MAX_PENDING", "5"))       # tope de propuestas sin decidir (no satura el panel)

# --- consolidación de memoria ("dreaming", patrón OpenClaw/Hermes) ----------
# aprendido.md crece sin freno y se le cuela lo efímero. Una vez al día el Curator
# reescribe la lista: fusiona duplicados, resuelve contradicciones por recencia,
# tira lo atado a una fecha (caduca) y la recorta a un tope. Siempre con backup
# atómico antes de sobrescribir: nada se pierde nunca.
CONSOLIDATE_EVERY = int(os.getenv("CURATOR_CONSOLIDATE_EVERY", "72"))  # ~24 h con INTERVAL=1200 s
CONSOLIDATE_MIN = int(os.getenv("CURATOR_CONSOLIDATE_MIN", "6"))       # no consolida con < N hechos
MAX_FACTS = int(os.getenv("CURATOR_MAX_FACTS", "50"))                  # tope de hechos en aprendido.md
FACTS_BAK_KEEP = 3                                                     # backups que se conservan

_PROPOSE = (
    "Eres un consejero que ayuda a mejorar a Jarvis, el mayordomo de José. Lee esta conversación y propón "
    "COMO MÁXIMO 2 mejoras CONCRETAS para servirle mejor: algo que merezca añadir a su perfil, una preferencia "
    "de trato o tono que hayas notado, o una rutina suya. Devuelve SOLO un array JSON; cada elemento con "
    '{"obs":"qué has observado, una frase","aplicar":"la frase exacta a añadir a su perfil, en tercera persona"}. '
    "Si no hay nada que proponer, devuelve []. Conversación:\n"
)
LLM = os.getenv("LLM_BASE", "http://litellm:4000/v1")
LLM_KEY = os.getenv("LITELLM_API_KEY", "sk-litellm")
INTERVAL = int(os.getenv("CURATOR_INTERVAL", "1200"))     # 20 min

_EXTRACT = (
    "Eres el archivero de un mayordomo. Lee esta conversación entre José y su asistente Jarvis y "
    "extrae los HECHOS DURABLES y ÚTILES sobre José que merezca recordar a largo plazo: gustos, "
    "preferencias, personas de su entorno (nombres, relación), rutinas, datos personales, decisiones, "
    "proyectos en marcha. NO incluyas nada EFÍMERO ni atado a una fecha/momento: la hora, el tiempo, una "
    "pregunta puntual, lo que Jarvis hizo, ni citas, reuniones o eventos concretos ('un curso mañana', "
    "'reunión el viernes', 'esta semana'). Eso caduca y NO es un hecho durable. TAMPOCO captures: estados "
    "de ánimo o quejas del momento ('hoy está cansado', 'le molestó X'), fallos técnicos o que 'algo no "
    "funciona' (eso se arregla, no es un rasgo suyo), ni detalles de una tarea puntual de un solo uso. "
    "Captura la PREFERENCIA, el dato o la corrección DURADERA, nunca el problema o el humor pasajero. "
    "Extrae SOLO lo que José haya dicho o se deduzca CLARAMENTE de la conversación; NUNCA inventes datos ni "
    "añadas detalles que no estén. Devuelve cada hecho en UNA línea (sin numerar), frase breve en tercera "
    "persona ('A José le gusta…', 'La pareja de José se llama…'). Máximo 8. Si no hay nada nuevo que merezca "
    "recordar, responde solo: NADA.\n\nConversación:\n"
)

_CONSOLIDATE = (
    "Eres el archivero de un mayordomo. Aquí tienes la lista de hechos que Jarvis ha aprendido sobre José. "
    "Reescríbela MEJORÁNDOLA, sin perder información útil:\n"
    "1) FUSIONA hechos duplicados o muy relacionados en una sola línea clara.\n"
    "2) RESUELVE contradicciones quedándote con lo más reciente: las líneas de ABAJO son más nuevas.\n"
    "3) ELIMINA lo EFÍMERO que se haya colado: cualquier cosa atada a una fecha o momento concreto "
    "('mañana', 'esta semana', 'el viernes', una cita, reunión o evento de agenda puntual). No son durables.\n"
    "4) NO inventes NADA ni añadas datos que no estén en la lista. Solo reorganiza, fusiona y limpia.\n"
    f"Devuelve SOLO la lista final en viñetas (una por línea, empezando por '- '), máximo {MAX_FACTS} líneas, "
    "en tercera persona. Si tras limpiar no queda ningún hecho durable, responde solo: NADA.\n\nLista actual:\n"
)


def _last_ts() -> float:
    try:
        return float(json.loads(STATE.read_text(encoding="utf-8")).get("ts", 0))
    except Exception:
        return 0.0


def _set_ts(ts: float) -> None:
    try:
        STATE.write_text(json.dumps({"ts": ts}), encoding="utf-8")
    except Exception:
        pass


def _recent_convo(since: float):
    if not DB.exists():
        return [], since
    c = sqlite3.connect(DB)
    try:
        rows = c.execute("SELECT ts,kind,payload FROM events WHERE ts>? AND kind IN "
                         "('user_said','assistant_said') ORDER BY ts", (since,)).fetchall()
    finally:
        c.close()
    lines, maxts = [], since
    for ts, kind, pl in rows:
        try:
            text = (json.loads(pl) or {}).get("text", "").strip()
        except Exception:
            text = (pl or "").strip()
        if not text or text[:1] in "<{[":
            continue
        lines.append(("José" if kind == "user_said" else "Jarvis") + ": " + text)
        maxts = ts
    return lines, maxts


async def _llm(prompt: str) -> str:
    body = {"model": "jarvis-main", "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 300, "extra_body": {"reasoning_effort": "none"}}
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{LLM}/chat/completions", json=body,
                          headers={"Authorization": "Bearer " + LLM_KEY},
                          timeout=aiohttp.ClientTimeout(total=40)) as r:
            j = await r.json()
    return (j["choices"][0]["message"].get("content") or "").strip()


def _merge(new_lines: list[str]) -> list[str]:
    try:
        existing = FACTS.read_text(encoding="utf-8")
    except Exception:
        existing = ""
    have = existing.lower()
    added = []
    for ln in new_lines:
        ln = re.sub(r"^[\s\-•*\d.)]+", "", ln).strip()    # quita viñetas y numeración
        if len(ln) < 8 or ln.upper().startswith("NADA"):
            continue
        if ln.lower()[:42] in have:                       # dedup simple por prefijo
            continue
        added.append(ln)
        have += "\n" + ln.lower()
    if added:
        with open(FACTS, "a", encoding="utf-8") as f:
            if not existing:
                f.write("# Lo que Jarvis ha aprendido de José\n\n")
            for ln in added:
                f.write(f"- {ln}\n")
    return added


def _read_facts() -> tuple[bool, list[str]]:
    """Devuelve (existe, lista de hechos) leyendo las viñetas de aprendido.md."""
    try:
        raw = FACTS.read_text(encoding="utf-8")
    except Exception:
        return False, []
    bullets = []
    for ln in raw.splitlines():
        s = ln.strip()
        if s.startswith("- "):
            bullets.append(s[2:].strip())
    return True, bullets


async def consolidate_once() -> tuple[int, int]:
    """Pasada diaria sobre el almacén de hechos: aplica DECAY (active->stale->archived
    por antigüedad sin verse/recordarse) y REGENERA aprendido.md como la vista rankeada
    de los hechos ACTIVE. Backup del .md antes, por seguridad. Devuelve (total, activos)."""
    import facts
    try:                                          # backup del .md antes de regenerar
        if FACTS.exists():
            ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(FACTS, FACTS.parent / f"aprendido.md.bak.{ts}")
            for old in sorted(FACTS.parent.glob("aprendido.md.bak.*"))[:-FACTS_BAK_KEEP]:
                old.unlink()
    except Exception as e:
        logger.warning(f"[curator] backup consolidación: {e}")
    counts = facts.decay()
    n = facts.render_prompt()
    total = sum(counts.values()) if counts else n
    return total, n


async def tick_once() -> list[str]:
    since = _last_ts()
    lines, maxts = _recent_convo(since)
    if len(lines) < 4:                                    # poca conversación nueva
        return []
    out = await _llm(_EXTRACT + "\n".join(lines[-60:]))
    _set_ts(maxts)
    import facts
    seen = facts.bump_seen("\n".join(lines))          # refresca hechos re-mencionados (frecuencia)
    added = []
    if out and not out.strip().upper().startswith("NADA"):
        for ln in out.splitlines():
            ln2 = re.sub(r"^[\s\-•*\d.)]+", "", ln).strip()
            if facts.add_fact(ln2):
                added.append(ln2)
    if added or seen:
        facts.render_prompt()                         # regenera aprendido.md (vista rankeada por uso)
    return added


def _last_lines(limit: int = 50) -> list[str]:
    if not DB.exists():
        return []
    c = sqlite3.connect(DB)
    try:
        rows = c.execute("SELECT kind,payload FROM events WHERE kind IN ('user_said','assistant_said') "
                         "ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    finally:
        c.close()
    out = []
    for kind, pl in reversed(rows):
        try:
            t = (json.loads(pl) or {}).get("text", "").strip()
        except Exception:
            t = (pl or "").strip()
        if t and t[:1] not in "<{[":
            out.append(("José" if kind == "user_said" else "Jarvis") + ": " + t)
    return out


def _load_props() -> list:
    try:
        return json.loads(PROPS.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_props(p: list) -> None:
    try:
        tmp = PROPS.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, PROPS)
    except Exception:
        pass


async def propose_once() -> int:
    """Propone mejoras (perfil/tono/rutina) a partir de la conversación reciente.
    Quedan PENDIENTES en /logs/propuestas.json; José las aprueba/rechaza en el panel."""
    lines = _last_lines(50)
    if len(lines) < 6:
        return 0
    if sum(1 for p in _load_props() if p.get("estado") == "pendiente") >= MAX_PENDING:
        return 0                                          # no apiles propuestas sin decidir
    out = await _llm(_PROPOSE + "\n".join(lines))
    m = re.search(r"\[.*\]", out, re.S)
    if not m:
        return 0
    try:
        items = json.loads(m.group(0))
    except Exception:
        return 0
    props = _load_props()
    have = " ".join(p.get("aplicar", "").lower() for p in props)
    added, new_props = 0, []
    for it in items if isinstance(items, list) else []:
        ap = (it.get("aplicar") or "").strip()
        if len(ap) < 8 or ap.lower()[:30] in have:
            continue
        p = {"id": f"{int(time.time()*1000)}{added}", "obs": (it.get("obs") or "").strip(),
             "aplicar": ap, "estado": "pendiente", "ts": time.time(), "pushed": False}
        props.append(p)
        new_props.append(p)
        have += " " + ap.lower()
        added += 1
    if added:
        _save_props(props)
        for p in new_props:                               # empuja cada nueva al móvil con botones
            await _push_proposal_to_telegram(p)
            p["pushed"] = True
        _save_props(props)
    return added


_REWORK = (
    "José ha pedido REFORMULAR esta sugerencia de mejora de su perfil. Reescríbela con OTRAS palabras, "
    "manteniendo el fondo, más natural o más concreta. Devuelve SOLO la frase final en tercera persona, "
    "una sola línea, sin comillas.\n"
)


async def _push_proposal_to_telegram(p: dict) -> None:
    """Empuja una propuesta al móvil con botones inline (Aprobar / Rechazar / Reformular)."""
    try:
        import telegram
        obs = (p.get("obs") or "").strip()
        text = "🌱 Propuesta de Jarvis\n" + (obs + "\n\n" if obs else "") + "➕ " + (p.get("aplicar") or "")
        kb = {"inline_keyboard": [[
            {"text": "✅ Aprobar", "callback_data": f"prop:{p['id']}:aprobar"},
            {"text": "❌ Rechazar", "callback_data": f"prop:{p['id']}:rechazar"},
            {"text": "✏️ Reformular", "callback_data": f"prop:{p['id']}:reformular"},
        ]]}
        await telegram.send(text, reply_markup=kb)
    except Exception as e:
        logger.warning(f"[curator] push telegram: {e}")


async def rework_requested() -> int:
    """Reprocesa las propuestas que José pidió 'reformular' (estado revision_requested):
    pide al LLM una versión distinta, crea una nueva pendiente (y la empuja), y marca la
    vieja como superseded. Cierra el bucle de aprobaciones (robado de Paperclip)."""
    props = _load_props()
    pend = [p for p in props if p.get("estado") == "revision_requested"]
    if not pend:
        return 0
    n = 0
    for old in pend:
        out = await _llm(_REWORK + f"Observación: {old.get('obs','')}\nFrase original: {old.get('aplicar','')}")
        first = ""
        if out:
            ls = out.strip().strip('"').splitlines()
            first = ls[0].strip() if ls else ""
        ap = re.sub(r"^[\s\-•*\d.)]+", "", first).strip()
        old["estado"] = "superseded"
        if len(ap) >= 8:
            np = {"id": f"{int(time.time()*1000)}{n}", "obs": old.get("obs", ""), "aplicar": ap,
                  "estado": "pendiente", "ts": time.time(), "pushed": False}
            props.append(np)
            await _push_proposal_to_telegram(np)
            np["pushed"] = True
            n += 1
    _save_props(props)
    return n


class Curator:
    def __init__(self):
        self._n = 0

    async def run(self) -> None:
        await asyncio.sleep(120)                          # deja arrancar
        try:                                              # migra aprendido.md -> tabla facts (1 vez)
            import facts
            m = facts.migrate_from_md()
            if m:
                logger.info(f"[curator] migrados {m} hechos de aprendido.md al almacén")
        except Exception as e:
            logger.warning(f"[curator] migración facts: {e}")
        logger.info("[curator] en marcha")
        while True:
            try:
                added = await tick_once()
                if added:
                    logger.info(f"[curator] aprendidos {len(added)} hechos nuevos de José")
                self._n += 1
                if self._n % PROPOSE_EVERY == 0:
                    p = await propose_once()
                    if p:
                        logger.info(f"[curator] {p} propuestas de mejora nuevas (pendientes de aprobar)")
                r = await rework_requested()              # cada ciclo: responde a los "reformular" de José
                if r:
                    logger.info(f"[curator] {r} propuestas reformuladas y reenviadas")
                if self._n % CONSOLIDATE_EVERY == 0:      # ~1 vez al día: limpia y compacta aprendido.md
                    a, b = await consolidate_once()
                    if b != a:
                        logger.info(f"[curator] memoria consolidada: {a} -> {b} hechos")
            except Exception as e:
                logger.warning(f"curator: {e}")
            await asyncio.sleep(INTERVAL)


if __name__ == "__main__":                                # uso manual: python curator.py --consolidate
    import sys
    if "--consolidate" in sys.argv:
        a, b = asyncio.run(consolidate_once())
        print(f"consolidación: {a} -> {b} hechos")
    else:
        print("uso: python curator.py --consolidate")
