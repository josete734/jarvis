"""Tests del cron en lenguaje natural (Bloque 3): parsing y cálculo de próximo disparo."""

import time

import cron


def test_parse_normalized():
    assert cron.parse_schedule("cada:30m") == {"kind": "interval", "secs": 1800}
    assert cron.parse_schedule("cada:2h")["secs"] == 7200
    assert cron.parse_schedule("diario:08:00") == {"kind": "daily", "hh": 8, "mm": 0}
    s = cron.parse_schedule("semanal:lun:09:00")
    assert s["kind"] == "weekly" and s["dow"] == 0 and s["hh"] == 9 and s["mm"] == 0


def test_parse_natural_fallback():
    assert cron.parse_schedule("cada día a las 8")["kind"] == "daily"
    assert cron.parse_schedule("todos los días a las 7:30") == {"kind": "daily", "hh": 7, "mm": 30}
    assert cron.parse_schedule("cada 30 minutos")["secs"] == 1800
    assert cron.parse_schedule("cada 2 horas")["secs"] == 7200
    assert cron.parse_schedule("cada hora")["secs"] == 3600
    assert cron.parse_schedule("cada lunes a las 9")["dow"] == 0


def test_parse_invalid():
    assert cron.parse_schedule("mañana quizás") is None
    assert cron.parse_schedule("") is None
    assert cron.parse_schedule(None) is None


def test_compute_next_interval():
    assert cron.compute_next({"kind": "interval", "secs": 1800}, 1000.0) == 2800.0
    # nunca por debajo de 60s
    assert cron.compute_next({"kind": "interval", "secs": 5}, 1000.0) == 1060.0


def test_compute_next_daily_is_future_within_a_day():
    now = time.time()
    nxt = cron.compute_next({"kind": "daily", "hh": 3, "mm": 0}, now)
    assert nxt > now and (nxt - now) <= 86400


def test_compute_next_weekly_is_future_within_a_week():
    now = time.time()
    nxt = cron.compute_next({"kind": "weekly", "dow": 0, "hh": 9, "mm": 0}, now)
    assert nxt > now and (nxt - now) <= 7 * 86400


def test_describe():
    assert "30 min" in cron.describe({"kind": "interval", "secs": 1800})
    assert "08:00" in cron.describe({"kind": "daily", "hh": 8, "mm": 0})
    assert "lun" in cron.describe({"kind": "weekly", "dow": 0, "hh": 9, "mm": 0})
