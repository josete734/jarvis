"""Audit log inmutable (robado de Paperclip `activity_log.ts`).

Cada acción mutante se traza a un ACTOR (jose / telegram / system / curator) con su
acción jerárquica, el recurso afectado y un detalle. Vive en /logs/events.db, en una
tabla con triggers que **prohíben UPDATE/DELETE** -> inmutabilidad real, no por
convención. Lo usa el panel para las decisiones sobre propuestas/perfil, y queda
disponible aquí para futuros escritores del orquestador (p.ej. `encargar`).
"""

import json
import time

from loguru import logger

_inited = False


def ensure(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS audit_log ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, actor TEXT, action TEXT,"
        " entity_type TEXT, entity_id TEXT, details TEXT)")
    conn.execute("CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log "
                 "BEGIN SELECT RAISE(ABORT, 'audit_log es inmutable'); END")
    conn.execute("CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log "
                 "BEGIN SELECT RAISE(ABORT, 'audit_log es inmutable'); END")
    conn.commit()


def audit(actor: str, action: str, entity_type: str, entity_id: str, details: dict | None = None) -> None:
    global _inited
    try:
        import events
        conn = events._db()
        if not _inited:
            ensure(conn)
            _inited = True
        conn.execute(
            "INSERT INTO audit_log(ts, actor, action, entity_type, entity_id, details) VALUES (?,?,?,?,?,?)",
            (time.time(), actor, action, entity_type, entity_id, json.dumps(details or {}, ensure_ascii=False)))
        conn.commit()
    except Exception as e:
        logger.warning(f"audit failed: {e}")
