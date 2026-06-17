"""Tests del almacén de hechos con recall + decay (refactor de memoria)."""

import sqlite3
import time

import facts


def _setup(tmp_path):
    facts.DB = tmp_path / "events.db"
    facts.FACTS_MD = tmp_path / "aprendido.md"


def test_add_and_dedupe(tmp_path):
    _setup(tmp_path)
    assert facts.add_fact("A José le gusta la pesca en el pantano de Tarragona") is True
    assert facts.add_fact("A José le gusta la pesca en el pantano de Tarragona") is False
    c = sqlite3.connect(facts.DB)
    n, seen = c.execute("SELECT COUNT(*), MAX(seen_count) FROM facts").fetchone()
    c.close()
    assert n == 1 and seen == 2          # no duplica; refresca seen_count


def test_recall_bumps_count(tmp_path):
    _setup(tmp_path)
    facts.add_fact("La pareja de José se llama María")
    hits = facts.recall("cómo se llama su pareja María")
    assert any("María" in h for h in hits)
    c = sqlite3.connect(facts.DB)
    rc = c.execute("SELECT recall_count FROM facts").fetchone()[0]
    c.close()
    assert rc == 1


def test_decay_active_stale_archived(tmp_path):
    _setup(tmp_path)
    facts.add_fact("Dato que nadie vuelve a mencionar nunca")
    c = sqlite3.connect(facts.DB)
    old = time.time() - (facts.STALE_DAYS + 5) * 86400
    c.execute("UPDATE facts SET last_seen=?, created=?", (old, old))
    c.commit(); c.close()
    assert facts.decay().get("stale") == 1
    c = sqlite3.connect(facts.DB)
    older = time.time() - (facts.ARCHIVE_DAYS + 5) * 86400
    c.execute("UPDATE facts SET last_seen=?, created=?, state='active'", (older, older))
    c.commit(); c.close()
    assert facts.decay().get("archived") == 1


def test_render_active_ranked_by_recency(tmp_path):
    _setup(tmp_path)
    facts.add_fact("Hecho A reciente")
    facts.add_fact("Hecho B antiguo")
    c = sqlite3.connect(facts.DB)
    old = time.time() - 20 * 86400
    c.execute("UPDATE facts SET last_seen=?, created=? WHERE text LIKE 'Hecho B%'", (old, old))
    c.commit(); c.close()
    assert facts.render_prompt() == 2
    body = facts.FACTS_MD.read_text(encoding="utf-8")
    assert body.index("Hecho A") < body.index("Hecho B")   # el reciente, primero


def test_archived_not_in_prompt(tmp_path):
    _setup(tmp_path)
    facts.add_fact("Hecho activo visible")
    facts.add_fact("Hecho que será archivado")
    c = sqlite3.connect(facts.DB)
    c.execute("UPDATE facts SET state='archived' WHERE text LIKE 'Hecho que%'")
    c.commit(); c.close()
    facts.render_prompt()
    body = facts.FACTS_MD.read_text(encoding="utf-8")
    assert "activo visible" in body and "será archivado" not in body


def test_bump_seen_refreshes(tmp_path):
    _setup(tmp_path)
    facts.add_fact("A José le interesa la pesca con cebo en Tarragona")
    assert facts.bump_seen("hoy hemos vuelto a hablar de pesca y de Tarragona") >= 1


def test_migrate_idempotent(tmp_path):
    _setup(tmp_path)
    facts.FACTS_MD.write_text("# x\n\n- Hecho migrado uno\n- Hecho migrado dos\n", encoding="utf-8")
    assert facts.migrate_from_md() == 2
    assert facts.migrate_from_md() == 0
