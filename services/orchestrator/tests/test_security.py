"""Tests de la confirmación verbal y el taint (PLAN_FINAL §9.1.1, §9.1.6).

Lo crítico: una acción side-effect SOLO se ejecuta si la última transcripción
REAL del usuario fue afirmativa y reciente. El LLM (o un contenido web) no puede
fabricar ese "sí".
"""

import asyncio

import pytest

from security_core import AFFIRMATIVE_RE, CONFIRM_TTL_SECS, SecurityState

AFFIRMATIVE = ["sí", "vale", "ok", "adelante", "hazlo", "claro que sí", "de acuerdo", "dale"]
NEGATIVE = ["no", "ni hablar", "para nada", "todavía no", "espera"]

# Declinan PERO contienen un token afirmativo como subcadena. El regex puro las
# matchearía; por eso la decisión real pasa por user_just_affirmed (guard de negación).
EXPLOIT_NEGATIONS = [
    "no, no lo hagas, no vale la pena",
    "no lo confirmo todavía",
    "déjalo, no procede ahora",
    "ni se te ocurra, ok",
]


@pytest.mark.parametrize("text", AFFIRMATIVE)
def test_affirmative_phrases_match(text):
    assert AFFIRMATIVE_RE.search(text)


@pytest.mark.parametrize("text", NEGATIVE)
def test_negative_phrases_do_not_match(text):
    assert not AFFIRMATIVE_RE.search(text)


@pytest.mark.parametrize("text", EXPLOIT_NEGATIONS)
def test_negation_with_affirmative_token_does_not_authorize(text):
    s = SecurityState()
    called = []

    async def execute(args):
        called.append(args)
        return {"ok": True}

    s.on_user_transcription(text)
    s.request_confirmation("crear_recordatorio", {"x": 1}, execute)
    result = asyncio.run(s.try_execute_pending())

    assert result["status"] == "denied"   # la negación gana sobre el token afirmativo
    assert called == []


def test_taint_set_and_cleared_on_new_user_turn():
    s = SecurityState()
    assert s.tainted is False
    s.mark_tainted("web_read")
    assert s.tainted is True
    s.on_user_transcription("hola")      # un nuevo turno del usuario limpia el taint
    assert s.tainted is False


def test_no_pending_action():
    s = SecurityState()
    result = asyncio.run(s.try_execute_pending())
    assert result["status"] == "error"


def test_executes_with_fresh_affirmative():
    s = SecurityState()
    called = []

    async def execute(args):
        called.append(args)
        return {"ok": True, "args": args}

    s.on_user_transcription("sí, hazlo")
    s.request_confirmation("crear_recordatorio", {"texto": "leche"}, execute)
    result = asyncio.run(s.try_execute_pending())

    assert result == {"ok": True, "args": {"texto": "leche"}}
    assert called == [{"texto": "leche"}]


def test_denied_without_affirmative():
    s = SecurityState()
    called = []

    async def execute(args):
        called.append(args)
        return {"ok": True}

    s.on_user_transcription("no, déjalo")
    s.request_confirmation("crear_recordatorio", {"texto": "x"}, execute)
    result = asyncio.run(s.try_execute_pending())

    assert result["status"] == "denied"
    assert called == []                  # la acción NO se ejecutó


def test_denied_when_affirmative_is_stale():
    s = SecurityState()
    called = []

    async def execute(args):
        called.append(args)
        return {"ok": True}

    s.on_user_transcription("sí")
    s.last_user_ts -= CONFIRM_TTL_SECS + 10     # el "sí" caducó
    s.request_confirmation("crear_recordatorio", {"texto": "x"}, execute)
    result = asyncio.run(s.try_execute_pending())

    assert result["status"] == "denied"
    assert called == []


def test_expired_pending():
    s = SecurityState()

    async def execute(args):
        return {"ok": True}

    s.on_user_transcription("sí")
    s.request_confirmation("crear_recordatorio", {"texto": "x"}, execute)
    s.pending.created -= CONFIRM_TTL_SECS + 10   # la confirmación pendiente caducó
    result = asyncio.run(s.try_execute_pending())

    assert result["status"] == "expired"
