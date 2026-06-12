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


def _demux(raw: bytes) -> str:
    """De-multiplexa el stream de logs de Docker (no-TTY): cabeceras de 8 bytes
    [tipo,0,0,0,size(4 BE)] + payload. Si no es multiplexado (TTY), decodifica crudo."""
    out, i, n = [], 0, len(raw)
    while i + 8 <= n:
        if raw[i] not in (0, 1, 2) or raw[i + 1 : i + 4] != b"\x00\x00\x00":
            return raw.decode("utf-8", "replace")
        size = int.from_bytes(raw[i + 4 : i + 8], "big")
        out.append(raw[i + 8 : i + 8 + size].decode("utf-8", "replace"))
        i += 8 + size
    return "".join(out) or raw.decode("utf-8", "replace")


async def get_logs(name: str, tail: int = 200) -> str:
    """Últimas líneas de log de un contenedor (requiere LOGS=1 en el socket-proxy)."""
    url = (f"{DOCKER_HOST}/containers/{name}/logs"
           f"?stdout=1&stderr=1&tail={int(tail)}&timestamps=1")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return f"(no se pudieron leer logs: HTTP {resp.status})"
                return _demux(await resp.read())
    except Exception as e:
        return f"(error leyendo logs: {e})"
