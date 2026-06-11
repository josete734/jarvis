"""Conexión de la seguridad al pipeline de Pipecat (PLAN_FINAL §9.1).

La lógica pura (SecurityState, confirmación, taint) vive en security_core.py
para poder testearla sin Pipecat. Este módulo re-exporta esos símbolos (para no
romper imports existentes) y añade el FrameProcessor que vuelca las
transcripciones reales del usuario en el SecurityState.
"""

from loguru import logger

from pipecat.frames.frames import Frame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection

import events

# Re-export: `from security import SecurityState, ...` sigue funcionando.
from security_core import (  # noqa: F401
    AFFIRMATIVE_RE,
    CONFIRM_TTL_SECS,
    PendingAction,
    SecurityState,
)


class TranscriptWatcher(FrameProcessor):
    """Records real user transcriptions into SecurityState (and clears taint).

    Clave de seguridad: la confirmación de acciones se valida contra la ÚLTIMA
    transcripción real del usuario (capturada aquí), no contra lo que el LLM
    diga — así un contenido web no puede fabricar el "sí" del usuario.
    """

    def __init__(self, security: SecurityState, gate=None, **kwargs):
        super().__init__(**kwargs)
        self._security = security
        self._gate = gate                  # WakeWordGate: lo mantenemos despierto al hablar

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame) and frame.text:
            self._security.on_user_transcription(frame.text)
            if self._gate is not None:
                # Sin esto el gate se duerme a los WAKE_TIMEOUT_SECS aunque la
                # conversación siga (las TranscriptionFrame no repasan por el gate).
                self._gate.notify_user_activity()
            # La reflexión nocturna (reflect.py) lee el kind 'user_said' de
            # events.db; sin esto el transcript diario queda vacío.
            events.log_event("user_said", {"text": frame.text})
        await self.push_frame(frame, direction)
