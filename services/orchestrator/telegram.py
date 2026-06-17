"""Push a Telegram (bot mycroft_neo_bot) para avisos proactivos al móvil.

Auto-descubre el chat_id desde getUpdates la primera vez (José solo tiene que
escribirle /start al bot) y lo cachea en /logs. Si TELEGRAM_TOKEN no está, no hace nada.
"""

import json
import os
from pathlib import Path

import aiohttp
from loguru import logger

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
_CHAT_FILE = Path("/logs/telegram_chat.txt")
_API = "https://api.telegram.org/bot{}".format


async def _chat_id() -> str | None:
    cid = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if cid:
        return cid
    try:
        cid = _CHAT_FILE.read_text(encoding="utf-8").strip()
        if cid:
            return cid
    except Exception:
        pass
    if not TOKEN:
        return None
    try:                                              # auto-descubrir: último que escribió
        async with aiohttp.ClientSession() as s:
            async with s.get(_API(TOKEN) + "/getUpdates",
                             timeout=aiohttp.ClientTimeout(total=8)) as r:
                ups = (await r.json()).get("result", [])
        for u in reversed(ups):
            ch = (u.get("message") or u.get("edited_message") or {}).get("chat", {})
            if ch.get("id"):
                cid = str(ch["id"])
                try:
                    _CHAT_FILE.write_text(cid, encoding="utf-8")
                except Exception:
                    pass
                return cid
    except Exception as e:
        logger.warning(f"telegram getUpdates: {e}")
    return None


async def send(text: str, *, silent: bool = False) -> bool:
    if not TOKEN or not text:
        return False
    cid = await _chat_id()
    if not cid:
        return False
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(_API(TOKEN) + "/sendMessage",
                              json={"chat_id": cid, "text": text, "disable_notification": silent},
                              timeout=aiohttp.ClientTimeout(total=8)) as r:
                return r.status == 200
    except Exception as e:
        logger.warning(f"telegram send: {e}")
        return False
