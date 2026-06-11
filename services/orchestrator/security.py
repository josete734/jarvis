"""Agent security primitives (PLAN_FINAL §9.1).

Two mechanisms, both deterministic and OUTSIDE the LLM:

1) Verbal confirmation for side-effect tools (§9.1.1):
   - First call of a side-effect tool does NOT execute. It stores a
     PendingAction (single slot, TTL) and tells the LLM to repeat the action
     aloud and ask for confirmation.
   - Execution only happens via the builtin tool `confirmar_accion`, and ONLY
     if the last *actual user transcription* is an affirmative within the TTL.
     A web page can inject a fake tool call, but it cannot fabricate the
     user's spoken "sí" — that check is plain code, not model judgement.

2) Taint mode (§9.1.6): any web content in the current turn marks it tainted.
   While tainted, side-effect tools always require confirmation and memory
   writes are skipped. The taint clears on the NEXT user transcription.
"""

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from loguru import logger

from pipecat.frames.frames import Frame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection

CONFIRM_TTL_SECS = 60
AFFIRMATIVE_RE = re.compile(
    r"\b(s[ií]|confirmo|confirmado|adelante|hazlo|dale|procede|vale|ok|de acuerdo|claro que s[ií])\b",
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
        return fresh and bool(AFFIRMATIVE_RE.search(self.last_user_text or ""))

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


class TranscriptWatcher(FrameProcessor):
    """Records real user transcriptions into SecurityState (and clears taint)."""

    def __init__(self, security: SecurityState, **kwargs):
        super().__init__(**kwargs)
        self._security = security

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame) and frame.text:
            self._security.on_user_transcription(frame.text)
        await self.push_frame(frame, direction)
