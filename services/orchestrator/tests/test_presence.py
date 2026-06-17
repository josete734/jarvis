"""Tests del estado de presencia y routing (Fase B + Telegram-remoto)."""

import time

import pytest

# proactive importa pipecat; en el CI mínimo (sin pipecat) se salta este módulo.
# En el contenedor, con las deps reales, corre completo.
proactive = pytest.importorskip("proactive")
PRESENCE_TTL = proactive.PRESENCE_TTL
REMOTE_WINDOW = proactive.REMOTE_WINDOW
PresenceState = proactive.PresenceState


def test_failsafe_present_without_vision():
    # Sin cámara latiendo, se asume PRESENTE (no quedarse mudo). Comportamiento actual.
    assert PresenceState().is_present() is True


def test_seen_recently_is_present():
    p = PresenceState()
    p.beat("jose")
    assert p.vision_alive() and p.is_present("jose")


def test_vision_alive_but_not_seen_is_absent():
    p = PresenceState()
    now = time.time()
    p.last_beat = now                       # vision viva
    p.last_seen["jose"] = now - (PRESENCE_TTL + 10)   # pero no le ve hace rato
    assert p.is_present("jose") is False


def test_telegram_marks_remote_and_suppresses_presence():
    p = PresenceState()
    p.beat("jose")                          # aunque la cámara le viera
    p.mark_remote()                         # un mensaje de Telegram manda
    assert p.is_remote() and p.is_present("jose") is False


def test_remote_window_expires():
    p = PresenceState()
    p.last_remote_ts = time.time() - (REMOTE_WINDOW + 10)
    assert p.is_remote() is False
