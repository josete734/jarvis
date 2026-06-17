"""Clasificación accionable de errores del LLM (Bloque 4.3, patrón Hermes).

Jarvis solo habla con litellm (OpenAI-spec). Una respuesta puede ser OK (`choices`)
o un error (`error`). En vez de tragar todo en un `except` genérico y soltar "no he
podido pensar", clasificamos para decidir: reintentar (rate-limit), COMPRIMIR el
historial (contexto lleno), o rendirse con un mensaje específico (policy/auth).
"""


def classify(j: dict | None) -> dict:
    j = j or {}
    if j.get("choices") and not j.get("error"):
        return {"ok": True}
    err = j.get("error")
    msg = (err.get("message") if isinstance(err, dict) else err) or ""
    m = str(msg).lower()

    if any(k in m for k in ("rate limit", "rate_limit", "429", "too many", "overloaded", "capacity")):
        return {"ok": False, "kind": "rate", "retryable": True,
                "user": "Estoy un poco saturado ahora mismo, señor; deme un segundo."}
    if "context" in m and any(k in m for k in ("length", "long", "maximum", "exceed", "token")):
        return {"ok": False, "kind": "context", "compress": True,
                "user": "Llevamos mucha conversación; la resumo y sigo, señor."}
    if "content" in m and ("policy" in m or "filter" in m):
        return {"ok": False, "kind": "policy", "retryable": False,
                "user": "Eso no puedo tratarlo, señor."}
    if any(k in m for k in ("api key", "unauthorized", "401", "authentication", "invalid_api_key")):
        return {"ok": False, "kind": "auth", "retryable": False,
                "user": "Tengo un problema de credenciales con el modelo, señor; reviso."}
    if "timeout" in m or "timed out" in m:
        return {"ok": False, "kind": "timeout", "retryable": True,
                "user": "El modelo tarda más de la cuenta, señor; reintento."}
    # error desconocido o respuesta sin choices
    return {"ok": False, "kind": "unknown", "retryable": True,
            "user": "No he podido pensar la respuesta ahora mismo, señor; pruebe otra vez."}
