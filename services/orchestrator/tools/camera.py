"""ver_camara() — grabs one frame from the vision service and describes it via
the cloud vision model (PLAN_FINAL §3.2: /dev/video0 is exclusive to vision,
the orchestrator gets frames over internal HTTP)."""

import base64
import os

import aiohttp

VISION_BASE = os.getenv("VISION_BASE", "http://vision:8089")
LLM_BASE = os.getenv("LLM_BASE", "http://litellm:4000/v1")
API_KEY = os.getenv("LITELLM_API_KEY", "sk-litellm")


async def ver_camara(pregunta: str = "", security=None) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{VISION_BASE}/frame", timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return {"status": "error", "mensaje": "La cámara no está disponible ahora mismo."}
            jpeg = await resp.read()

    image_b64 = base64.b64encode(jpeg).decode()
    prompt = pregunta or "Describe brevemente y en español lo que se ve."

    payload = {
        "model": "jarvis-vision",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
            ],
        }],
        "max_tokens": 300,
    }
    headers = {"Authorization": f"Bearer {API_KEY}"}
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{LLM_BASE}/chat/completions", json=payload, headers=headers,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            data = await resp.json()

    try:
        return {"descripcion": data["choices"][0]["message"]["content"]}
    except (KeyError, IndexError):
        return {"status": "error", "detalle": str(data)[:300]}
