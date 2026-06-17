"""recordar — memoria entre sesiones (patrón Hermes): índice FTS5 sobre las
conversaciones de events.db. Jarvis BUSCA lo que José le contó en el pasado en
vez de depender solo del contexto reciente.
"""

import json
import re
import sqlite3
import time
from pathlib import Path

DB = Path("/logs/events.db")
_STOP = {"que", "como", "cual", "cuales", "donde", "cuando", "sobre", "para", "los",
         "las", "del", "una", "uno", "mis", "tus", "con", "por", "the", "dije", "dijiste",
         "conte", "conté", "hablamos", "recuerdas", "sabes"}


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB)
    c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS transcript_fts "
              "USING fts5(text, role UNINDEXED, ts UNINDEXED)")
    return c


def _sync(c: sqlite3.Connection) -> None:
    last = c.execute("SELECT max(ts) FROM transcript_fts").fetchone()[0] or 0
    rows = c.execute(
        "SELECT ts, kind, payload FROM events WHERE ts>? AND kind IN "
        "('user_said','assistant_said') ORDER BY ts", (last,)).fetchall()
    for ts, kind, pl in rows:
        try:
            text = (json.loads(pl) or {}).get("text", "").strip()
        except Exception:
            text = (pl or "").strip()
        if not text or text[:1] in ("<", "{", "["):
            continue
        role = "José" if kind == "user_said" else "Jarvis"
        c.execute("INSERT INTO transcript_fts(text, role, ts) VALUES (?,?,?)", (text, role, ts))
    c.commit()


def _match(consulta: str):
    words = re.findall(r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3,}", consulta or "")
    words = [w for w in words if w.lower() not in _STOP][:8]
    return " OR ".join(words) if words else None


def _rel(ts: float) -> str:
    s = time.time() - ts
    if s < 3600:
        return "hace un rato"
    if time.localtime(ts).tm_yday == time.localtime().tm_yday:
        return "hoy"
    d = int(s // 86400)
    return "ayer" if d <= 1 else f"hace {d} días"


async def recordar(consulta: str, security=None) -> dict:
    rec = []
    # 1) Hechos DURABLES del almacén (facts): bumpea su recall = señal de utilidad real,
    #    que alimenta el scoring/decay (lo que de verdad usas se queda fresco y prioritario).
    try:
        import facts
        for t in facts.recall(consulta)[:4]:
            rec.append({"cuando": "lo que sé de usted", "quien": "José", "texto": t[:160]})
    except Exception:
        pass
    # 2) Transcripts FTS5 (lo que se dijo en conversaciones pasadas).
    m = _match(consulta)
    if m and DB.exists():
        try:
            c = _conn()
            _sync(c)
            rows = c.execute(
                "SELECT text, role, ts FROM transcript_fts WHERE transcript_fts MATCH ? "
                "ORDER BY rank LIMIT 6", (m,)).fetchall()
            c.close()
            rec += [{"cuando": _rel(ts), "quien": role, "texto": text[:160]} for text, role, ts in rows]
        except Exception:
            pass
    if not rec:
        return {"recuerdos": [], "mensaje": "No recuerdo nada sobre eso, señor."}
    return {"recuerdos": rec}
