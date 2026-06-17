"""Núcleo de seguridad SIN dependencias de Pipecat — testeable de forma aislada.

La lógica de confirmación verbal y de taint (PLAN_FINAL §9.1) vive aquí para que
pueda probarse en CI sin instalar Pipecat ni hardware. El FrameProcessor que la
conecta al pipeline (TranscriptWatcher) está en security.py.
"""

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from loguru import logger

CONFIRM_TTL_SECS = 300   # 5 min: por Telegram el "sí" tarda; con 60s caducaba antes de confirmar
# Solo "sí" acentuado (no "si" condicional, que aparece en frases dubitativas).
AFFIRMATIVE_RE = re.compile(
    r"\b(sí|confirmo|confirmado|adelante|hazlo|dale|procede|vale|ok|de acuerdo|claro que sí)\b",
    re.IGNORECASE,
)
# Cualquier marcador de negación invalida el turno (fail-closed), aunque la frase
# contenga además un token afirmativo: "no, no vale la pena" NO debe autorizar.
NEGATION_RE = re.compile(
    r"\b(no|nunca|jam[áa]s|ni|tampoco|nada)\b",
    re.IGNORECASE,
)


@dataclass
class PendingAction:
    tool_name: str
    args: dict
    execute: Callable[[dict], Awaitable[Any]]
    created: float = field(default_factory=time.monotonic)
    token: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    @property
    def expired(self) -> bool:
        return time.monotonic() - self.created > CONFIRM_TTL_SECS


class SecurityState:
    def __init__(self):
        self.tainted: bool = False
        self.pending: PendingAction | None = None
        self.last_user_text: str = ""
        self.last_user_ts: float = 0.0
        self.dnd: bool = False                    # presence do-not-disturb (panel toggle)

    # -- taint ----------------------------------------------------------------

    def mark_tainted(self, source: str) -> None:
        if not self.tainted:
            logger.warning(f"Turn tainted by untrusted content ({source})")
        self.tainted = True

    def on_user_transcription(self, text: str) -> None:
        self.tainted = False                      # taint applies to one assistant turn
        self.last_user_text = text
        self.last_user_ts = time.monotonic()

    # -- confirmation ----------------------------------------------------------

    def request_confirmation(self, tool_name: str, args: dict, execute) -> dict:
        self.pending = PendingAction(tool_name=tool_name, args=args, execute=execute)
        logger.info(f"Pending confirmation [{self.pending.token}] {tool_name}({args})")
        return {
            "status": "pending_confirmation",
            "accion": tool_name,
            "parametros": args,
            "instruccion": (
                "Repite al usuario en una frase qué vas a hacer y con qué datos, "
                "y pídele confirmación explícita. Cuando el usuario confirme de "
                "viva voz, llama a la herramienta confirmar_accion."
            ),
        }

    def user_just_affirmed(self) -> bool:
        fresh = time.monotonic() - self.last_user_ts <= CONFIRM_TTL_SECS
        if not fresh:
            return False
        text = self.last_user_text or ""
        if NEGATION_RE.search(text):       # fail-closed ante cualquier negación
            return False
        return bool(AFFIRMATIVE_RE.search(text))

    async def try_execute_pending(self) -> dict:
        pending, self.pending = self.pending, None
        if pending is None:
            return {"status": "error", "mensaje": "No hay ninguna acción pendiente de confirmar."}
        if pending.expired:
            return {"status": "expired", "mensaje": "La confirmación caducó; vuelve a pedir la acción."}
        if not self.user_just_affirmed():
            # The LLM called confirmar_accion but the human never said yes.
            logger.warning(f"Blocked confirmar_accion without real user affirmative [{pending.token}]")
            return {
                "status": "denied",
                "mensaje": "No he oído una confirmación clara del usuario. La acción NO se ha ejecutado.",
            }
        logger.info(f"Executing confirmed action [{pending.token}] {pending.tool_name}")
        return await pending.execute(pending.args)
