"""Tests del clasificador de errores del LLM (Bloque 4.3)."""

import llm_errors as le


def test_ok_response():
    assert le.classify({"choices": [{"message": {"content": "hola"}}]}) == {"ok": True}


def test_rate_limit_retryable():
    r = le.classify({"error": {"message": "Rate limit exceeded (429), too many requests"}})
    assert not r["ok"] and r["kind"] == "rate" and r["retryable"]


def test_context_overflow_compresses():
    r = le.classify({"error": {"message": "This model's maximum context length is 8192 tokens"}})
    assert r["kind"] == "context" and r.get("compress")


def test_content_policy_not_retryable():
    r = le.classify({"error": {"message": "content policy violation / filtered"}})
    assert r["kind"] == "policy" and not r["retryable"]


def test_auth_error():
    r = le.classify({"error": {"message": "Invalid API key / unauthorized"}})
    assert r["kind"] == "auth" and not r["retryable"]


def test_timeout_retryable():
    r = le.classify({"error": {"message": "request timed out"}})
    assert r["kind"] == "timeout" and r["retryable"]


def test_unknown_and_empty():
    assert le.classify({"weird": 1})["kind"] == "unknown"
    assert le.classify(None)["kind"] == "unknown"
    assert not le.classify({})["ok"]
