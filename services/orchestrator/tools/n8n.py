"""n8n webhook caller with HMAC signing (PLAN_FINAL §9.1.5).

Signature: HMAC-SHA256(secret, f"{timestamp}.{raw_body}") hex, sent as
X-Jarvis-Signature + X-Jarvis-Timestamp. The first Code node of every
side-effect workflow re-computes it (timing-safe compare, 5 min window,
request-id dedupe). See n8n/workflows/recordatorio.example.json.
"""

import hashlib
import hmac
import json
import os
import time
import uuid

import aiohttp

N8N_BASE = os.getenv("N8N_BASE", "http://n8n:5678")
SECRET = os.getenv("N8N_WEBHOOK_SECRET", "")


async def call_webhook(path: str, **payload) -> dict:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    ts = str(int(time.time()))
    signature = hmac.new(SECRET.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-Jarvis-Timestamp": ts,
        "X-Jarvis-Signature": signature,
        "X-Jarvis-Request-Id": uuid.uuid4().hex,
    }
    url = f"{N8N_BASE}/webhook/{path}"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=body.encode(), headers=headers) as resp:
            text = await resp.text()
            if resp.status >= 400:
                return {"status": "error", "http": resp.status, "detalle": text[:300]}
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"status": "ok", "respuesta": text[:300]}
