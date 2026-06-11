"""Container status via docker-socket-proxy (GET-only). Never the raw socket."""

import os

import aiohttp

DOCKER_HOST = os.getenv("DOCKER_HOST", "tcp://socket-proxy:2375").replace("tcp://", "http://")


async def list_containers() -> list[dict]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{DOCKER_HOST}/containers/json?all=true",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                data = await resp.json()
    except Exception as e:
        return [{"name": "docker-socket-proxy", "state": "error", "status": str(e)}]
    return [
        {
            "name": (c.get("Names") or ["?"])[0].lstrip("/"),
            "state": c.get("State", "?"),
            "status": c.get("Status", ""),
        }
        for c in sorted(data, key=lambda c: (c.get("Names") or ["?"])[0])
    ]
