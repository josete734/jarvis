"""Agente de texto bidireccional por Telegram (Fase A — patrón OpenClaw/Hermes).

José le escribe por Telegram y Jarvis le contesta con el MISMO cerebro (GLM-5 vía
litellm), las MISMAS herramientas (tools/registry) y la MISMA memoria (events.db +
aprendido.md) que por voz, pero en modo texto (respuestas más largas, listas, enlaces).

- Long-polling getUpdates con offset persistido (un único lector del long-poll).
- Solo responde al dueño (TELEGRAM_OWNER_ID); a cualquier otro lo ignora en silencio.
- Bucle de chat-completions con tool-calling (mensaje -> LLM -> tool_calls? -> ejecuta
  -> re-LLM -> respuesta), tope de iteraciones anti-bucle.
- Cada turno se persiste en events.db como user_said/assistant_said (+channel=telegram)
  para que el Curator también aprenda y la tool `recordar` lo encuentre por FTS5.
- SecurityState PROPIO (aísla confirmaciones/taint del canal de voz).

Corre como task asyncio dentro del orquestador (junto a Heartbeat/Curator); NO toca
el pipeline de voz: el cerebro se llama por HTTP, no por Pipecat.
"""

import asyncio
import json
import os
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import aiohttp
from loguru import logger

import events
import llm_errors
import sysprompt
import telegram as tg
from security_core import SecurityState
from tools.registry import dispatch, tool_specs

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
OWNER = os.getenv("TELEGRAM_OWNER_ID", "").strip()
LLM = os.getenv("LLM_BASE", "http://litellm:4000/v1")
LLM_KEY = os.getenv("LITELLM_API_KEY", "sk-litellm")
_API = "https://api.telegram.org/bot{}".format
_OFFSET = Path("/logs/telegram_offset.txt")
_CHAT = Path("/logs/telegram_chat.txt")

MAX_TOOL_ITERS = int(os.getenv("TG_MAX_TOOL_ITERS", "5"))
MAX_TOKENS = int(os.getenv("TG_MAX_TOKENS", "700"))
MAX_TOOL_RESULT = int(os.getenv("TG_MAX_TOOL_RESULT", "4000"))   # cap del output de una tool
HISTORY = int(os.getenv("TG_HISTORY", "24"))          # turnos (user+assistant) en contexto
RL_PER_MIN = int(os.getenv("TG_RATELIMIT", "20"))     # mensajes/min máx del dueño

_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre"]


def _momento() -> str:
    n = datetime.now()
    return (f"\n\n## Momento actual (dato del sistema)\nAhora es {_DIAS[n.weekday()]} {n.day} de "
            f"{_MESES[n.month - 1]} de {n.year}, las {n.hour:02d}:{n.minute:02d} (hora de España).")


def _read_offset() -> int:
    try:
        return int(_OFFSET.read_text(encoding="utf-8").strip())
    except Exception:
        return 0


def _write_offset(off: int) -> None:
    try:
        _OFFSET.write_text(str(off), encoding="utf-8")
    except Exception:
        pass


async def _chat(messages: list, tools: list) -> dict:
    body = {"model": "jarvis-main", "messages": messages, "tools": tools,
            "max_tokens": MAX_TOKENS, "extra_body": {"reasoning_effort": "none"}}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{LLM}/chat/completions", json=body,
                              headers={"Authorization": "Bearer " + LLM_KEY},
                              timeout=aiohttp.ClientTimeout(total=120)) as r:
                j = await r.json()
    except Exception as e:                           # red/timeout -> error clasificable, no excepción
        return {"error": {"message": f"timeout {e}"}}
    # Registra el consumo para que el HUD lo cuente igual que el de voz (kind 'llm_usage').
    try:
        u = j.get("usage") or {}
        p = int(u.get("prompt_tokens", 0) or 0)
        c = int(u.get("completion_tokens", 0) or 0)
        cache = int((u.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0)
        if p or c:
            events.log_event("llm_usage", {"prompt": p, "completion": c, "cache": cache,
                                           "model": j.get("model", "") or "GLM-5",
                                           "channel": "telegram"})
    except Exception:
        pass
    return j


class TelegramAgent:
    def __init__(self):
        self._sec = SecurityState()                 # aislado del canal de voz
        self._hist: deque = deque(maxlen=HISTORY * 2)
        self._rl: deque = deque()                   # ts de mensajes recientes (rate-limit)

    # -- LLM turn -----------------------------------------------------------
    async def _think(self, text: str) -> str:
        self._sec.on_user_transcription(text)       # registra el "sí" escrito para confirmaciones
        # Confirmación DETERMINISTA (el LLM entraba en bucle re-llamando la tool en vez de
        # a confirmar_accion). Si hay una acción pendiente y José confirma, se ejecuta aquí
        # mismo; si la rechaza, se descarta. No se le deja la decisión al modelo.
        if self._sec.pending and not self._sec.pending.expired:
            if self._sec.user_just_affirmed():
                result = await self._sec.try_execute_pending()
                reply = (result or {}).get("mensaje") or "Hecho, señor."
                self._hist.append({"role": "user", "content": text})
                self._hist.append({"role": "assistant", "content": reply})
                return reply
            from security_core import NEGATION_RE
            if NEGATION_RE.search(text or ""):
                self._sec.pending = None
                reply = "Entendido, señor. Lo dejo."
                self._hist.append({"role": "user", "content": text})
                self._hist.append({"role": "assistant", "content": reply})
                return reply
            # respuesta ambigua: sigue el flujo normal; la pendiente caduca sola (TTL 60s)
        system = sysprompt.compose("texto") + _momento()
        messages = [{"role": "system", "content": system}] + list(self._hist) + \
                   [{"role": "user", "content": text}]
        specs = tool_specs()
        final = None
        retried = False
        for _ in range(MAX_TOOL_ITERS + 2):
            j = await _chat(messages, specs)
            cls = llm_errors.classify(j)
            if not cls["ok"]:
                if cls.get("compress") and len(self._hist) >= 4:   # contexto lleno: poda y reintenta
                    for _ in range(4):
                        if self._hist:
                            self._hist.popleft()
                    messages = [{"role": "system", "content": system}] + list(self._hist) + \
                               [{"role": "user", "content": text}]
                    continue
                if cls.get("retryable") and not retried:
                    retried = True
                    await asyncio.sleep(2)
                    continue
                logger.warning(f"[tg-agent] LLM error ({cls['kind']})")
                final = cls["user"]
                break
            msg = j["choices"][0]["message"]
            tcs = msg.get("tool_calls")
            if not tcs:
                final = (msg.get("content") or "").strip()
                break
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tcs})
            for tc in tcs:
                fn = (tc.get("function") or {}).get("name", "")
                try:
                    args = json.loads((tc["function"].get("arguments") or "{}"))
                except Exception:
                    args = {}
                result = await dispatch(fn, args, self._sec)
                content = json.dumps(result, ensure_ascii=False)
                if len(content) > MAX_TOOL_RESULT:    # 4.2: no inflar el contexto con outputs enormes
                    content = content[:MAX_TOOL_RESULT] + "…(resultado recortado)"
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": content})
        if not final:
            final = "Disculpe, señor, me he enredado con eso. ¿Puede reformularlo?"
        self._hist.append({"role": "user", "content": text})
        self._hist.append({"role": "assistant", "content": final})
        return final

    # -- per message --------------------------------------------------------
    async def _on_message(self, chat_id, text: str) -> None:
        try:                                        # un mensaje de Telegram = José NO está delante
            from proactive import PRESENCE
            PRESENCE.mark_remote()
        except Exception:
            pass
        now = time.time()
        while self._rl and now - self._rl[0] > 60:
            self._rl.popleft()
        if len(self._rl) >= RL_PER_MIN:
            await tg.send("Un momento, señor; va demasiado rápido para mí.")
            return
        self._rl.append(now)
        try:                                        # asegura el chat_id cacheado (para push)
            _CHAT.write_text(str(chat_id), encoding="utf-8")
        except Exception:
            pass
        events.log_event("user_said", {"text": text, "channel": "telegram"})
        try:                                        # "escribiendo…" para UX
            async with aiohttp.ClientSession() as s:
                await s.post(_API(TOKEN) + "/sendChatAction",
                             json={"chat_id": chat_id, "action": "typing"},
                             timeout=aiohttp.ClientTimeout(total=5))
        except Exception:
            pass
        reply = await self._think(text)
        await tg.send(reply)
        events.log_event("assistant_said", {"text": reply, "channel": "telegram"})
        logger.info(f"[tg-agent] respondido ({len(reply)} car)")

    # -- poll loop ----------------------------------------------------------
    async def _poll(self, offset: int) -> list:
        params = {"offset": offset, "timeout": 25, "allowed_updates": json.dumps(["message"])}
        async with aiohttp.ClientSession() as s:
            async with s.get(_API(TOKEN) + "/getUpdates", params=params,
                             timeout=aiohttp.ClientTimeout(total=35)) as r:
                return (await r.json()).get("result", [])

    async def run(self) -> None:
        if not TOKEN:
            logger.warning("[tg-agent] sin TELEGRAM_TOKEN: agente de texto desactivado")
            return
        if not OWNER:
            logger.warning("[tg-agent] sin TELEGRAM_OWNER_ID: por seguridad NO respondo a nadie")
            return
        await asyncio.sleep(20)                      # deja arrancar el pipeline
        offset = _read_offset()
        logger.info(f"[tg-agent] long-polling en marcha (owner={OWNER})")
        while True:
            try:
                ups = await self._poll(offset)
            except Exception as e:
                logger.warning(f"[tg-agent] poll: {e}")
                await asyncio.sleep(5)
                continue
            for u in ups:
                offset = u.get("update_id", offset - 1) + 1
                _write_offset(offset)
                msg = u.get("message")
                if not msg:
                    continue
                if str((msg.get("from") or {}).get("id")) != OWNER:
                    logger.info("[tg-agent] mensaje de un desconocido ignorado")
                    continue
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                try:
                    await self._on_message((msg.get("chat") or {}).get("id"), text)
                except Exception as e:
                    logger.exception(f"[tg-agent] on_message: {e}")
