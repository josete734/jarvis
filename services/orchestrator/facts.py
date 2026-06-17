"""Almacén estructurado de hechos durables sobre José — recall + decay REAL.

Sustituye la lista plana de aprendido.md por una tabla `facts` con metadatos:
cuándo se aprendió, cuándo se re-mencionó (last_seen) o se recuperó (last_recalled),
cuántas veces, y un estado (active/stale/archived). El Curator escribe aquí; el
fichero **aprendido.md se REGENERA** como la vista rankeada y acotada de los hechos
ACTIVE (sysprompt.py lo sigue leyendo igual). Así Jarvis prioriza lo que de verdad
usas y ARCHIVA (sin borrar, recuperable) lo que no vuelve a aparecer.

Scoring (para el orden/budget del prompt): recencia (half-life 14 d) + recall + frecuencia.
Decay: active -> stale (30 d sin verse/recordarse) -> archived (90 d). Reactiva si reaparece.
"""

import math
import os
import re
import sqlite3
import time
from pathlib import Path

DB = Path(os.getenv("EVENTS_DB", "/logs/events.db"))      # tests lo sobrescriben
FACTS_MD = Path(os.getenv("FACTS_MD", "/logs/aprendido.md"))
STALE_DAYS = int(os.getenv("FACTS_STALE_DAYS", "30"))
ARCHIVE_DAYS = int(os.getenv("FACTS_ARCHIVE_DAYS", "90"))
MAX_PROMPT = int(os.getenv("FACTS_MAX_PROMPT", "50"))
HALF_LIFE = 14.0   # días


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB)
    c.execute(
        "CREATE TABLE IF NOT EXISTS facts ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, created REAL,"
        " last_seen REAL, last_recalled REAL, seen_count INTEGER DEFAULT 1,"
        " recall_count INTEGER DEFAULT 0, state TEXT DEFAULT 'active')")
    return c


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").lower()).strip()


def _keywords(text: str) -> list[str]:
    stop = {"jose", "josé", "tiene", "esta", "está", "para", "con", "los", "las", "del", "una"}
    return [w for w in re.findall(r"[a-zñáéíóúü0-9]{4,}", _norm(text)) if w not in stop][:6]


def add_fact(text: str) -> bool:
    """Añade un hecho nuevo. Si ya existe (prefijo normalizado), lo REFRESCA en vez de
    duplicar. Devuelve True solo si era nuevo."""
    text = re.sub(r"^[\s\-•*\d.)]+", "", text or "").strip()
    if len(text) < 8 or text.upper().startswith("NADA"):
        return False
    key = _norm(text)[:42]
    c = _conn()
    try:
        for fid, ex in c.execute("SELECT id, text FROM facts").fetchall():
            if _norm(ex)[:42] == key:
                c.execute("UPDATE facts SET last_seen=?, seen_count=seen_count+1, state='active' "
                          "WHERE id=?", (time.time(), fid))
                c.commit()
                return False
        now = time.time()
        c.execute("INSERT INTO facts(text, created, last_seen, last_recalled) VALUES (?,?,?,NULL)",
                  (text, now, now))
        c.commit()
        return True
    finally:
        c.close()


def bump_seen(conversation_text: str) -> int:
    """Refresca (last_seen++) los hechos cuyos términos clave aparecen en la conversación
    nueva: señal de FRECUENCIA real que alimenta el scoring y frena el decay."""
    blob = _norm(conversation_text)
    if not blob:
        return 0
    c = _conn()
    now = time.time()
    n = 0
    try:
        for fid, text in c.execute("SELECT id, text FROM facts WHERE state!='archived'").fetchall():
            kw = _keywords(text)
            if kw and sum(1 for w in kw if w in blob) >= max(1, len(kw) // 3):
                c.execute("UPDATE facts SET last_seen=?, seen_count=seen_count+1, state='active' "
                          "WHERE id=?", (now, fid))
                n += 1
        c.commit()
    finally:
        c.close()
    return n


def recall(query: str) -> list[str]:
    """Busca hechos por palabras clave y BUMPEA su recall (señal de utilidad real)."""
    words = [w for w in re.findall(r"[a-zñáéíóúü0-9]{3,}", _norm(query))][:8]
    if not words:
        return []
    c = _conn()
    now = time.time()
    hits = []
    try:
        for fid, text in c.execute("SELECT id, text FROM facts WHERE state!='archived'").fetchall():
            nt = _norm(text)
            if any(w in nt for w in words):
                hits.append((fid, text))
        for fid, _ in hits:
            c.execute("UPDATE facts SET recall_count=recall_count+1, last_recalled=? WHERE id=?",
                      (now, fid))
        c.commit()
    finally:
        c.close()
    return [t for _, t in hits]


def decay() -> dict:
    """active->stale (30 d) ->archived (90 d). Reactiva stale si reapareció. Nunca borra."""
    c = _conn()
    now = time.time()
    try:
        c.execute("UPDATE facts SET state='archived' WHERE state IN ('active','stale') "
                  "AND ?-COALESCE(last_recalled,last_seen,created) > ?", (now, ARCHIVE_DAYS * 86400))
        c.execute("UPDATE facts SET state='stale' WHERE state='active' "
                  "AND ?-COALESCE(last_recalled,last_seen,created) > ?", (now, STALE_DAYS * 86400))
        c.execute("UPDATE facts SET state='active' WHERE state='stale' "
                  "AND ?-COALESCE(last_recalled,last_seen,created) <= ?", (now, STALE_DAYS * 86400))
        c.commit()
        counts = dict(c.execute("SELECT state, COUNT(*) FROM facts GROUP BY state").fetchall())
    finally:
        c.close()
    return counts


def _score(row: sqlite3.Row, now: float) -> float:
    last = row["last_recalled"] or row["last_seen"] or row["created"] or now
    age_days = max(0.0, (now - last) / 86400)
    recency = math.exp(-math.log(2) / HALF_LIFE * age_days)
    recall = min(1.0, (row["recall_count"] or 0) / 5.0)
    freq = min(1.0, (row["seen_count"] or 1) / 5.0)
    return recency * 0.5 + recall * 0.3 + freq * 0.2


def render_prompt() -> int:
    """Regenera aprendido.md con los hechos ACTIVE rankeados por score (top MAX_PROMPT).
    Escritura atómica. Devuelve cuántos hechos se han volcado."""
    c = _conn()
    c.row_factory = sqlite3.Row
    now = time.time()
    try:
        rows = c.execute("SELECT * FROM facts WHERE state='active'").fetchall()
    finally:
        c.close()
    rows = sorted(rows, key=lambda r: _score(r, now), reverse=True)[:MAX_PROMPT]
    body = "# Lo que Jarvis ha aprendido de José\n\n" + "".join(f"- {r['text']}\n" for r in rows)
    try:
        tmp = FACTS_MD.with_suffix(".md.tmp")
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, FACTS_MD)
    except Exception:
        pass
    return len(rows)


def migrate_from_md() -> int:
    """Una vez: si la tabla está vacía pero hay aprendido.md, importa sus viñetas."""
    c = _conn()
    try:
        if c.execute("SELECT COUNT(*) FROM facts").fetchone()[0] > 0:
            return 0
    finally:
        c.close()
    try:
        raw = FACTS_MD.read_text(encoding="utf-8")
    except Exception:
        return 0
    n = 0
    for ln in raw.splitlines():
        s = ln.strip()
        if s.startswith("- ") and add_fact(s[2:]):
            n += 1
    return n
