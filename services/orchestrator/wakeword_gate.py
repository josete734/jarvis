"""Wake-word gate — the only fully custom audio component (PLAN_FINAL §3.1).

Pipecat has no audio wake word (issue #1985, closed unimplemented). This
FrameProcessor sits right after transport.input() and drops InputAudioRawFrame
while asleep, so VAD/STT never run until "hey Jarvis" is detected.

Adapted from the community OpenWakeWordProcessor (Highgrove-Home
app-voice-assistant) against the specs verified in jun-2026:
  - openwakeword 0.6.0, ONNX framework (x86, avoids tflite/py3.12 issues)
  - 16 kHz mono int16, chunks of 1280 samples (80 ms)
  - Model.predict() returns {model_name: score}; internal streaming state
Expected load: ~1-3% of one core on the i5-10400T.
"""

import asyncio
import os
import time

import numpy as np
from loguru import logger
from openwakeword.model import Model

from pipecat.frames.frames import Frame, InputAudioRawFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection

from rest import REST

CHUNK_SAMPLES = 1280                  # 80 ms @ 16 kHz (openwakeword recommendation)
CHUNK_BYTES = CHUNK_SAMPLES * 2       # int16
REARM_COOLDOWN_SECS = 1.0             # avoid instant re-trigger after waking


class WakeWordGate(FrameProcessor):
    def __init__(
        self,
        *,
        model_path: str,
        threshold: float = 0.5,
        wake_timeout_secs: float = 45.0,
        probe=None,                      # VoiceStateObserver | None (estado HUD en vivo)
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._threshold = threshold
        self._timeout = wake_timeout_secs
        self._buffer = bytearray()
        self._awake = False
        self._last_wake = 0.0
        self._sleep_task: asyncio.Task | None = None
        self._probe = probe

        framework = os.getenv("WAKE_FRAMEWORK", "onnx")
        self._model = Model(
            wakeword_models=[model_path],
            inference_framework=framework,
            # VAD interno de openWakeWord desactivado (0.0) a propósito: con audio de nivel
            # bajo (mic USB lejano) anulaba el score antes de evaluarlo. Ajustable por env.
            vad_threshold=float(os.getenv("WAKE_VAD_THRESHOLD", "0.0")),
        )
        self._model_key = list(self._model.models.keys())[0]
        logger.info(f"WakeWordGate ready (model={model_path}, framework={framework})")

    # -- state ---------------------------------------------------------------

    def _renew_keepalive(self) -> None:
        """(Re)start the countdown back to sleep. Called on wake and on user activity."""
        if self._sleep_task and not self._sleep_task.done():
            self._sleep_task.cancel()
        self._sleep_task = asyncio.create_task(self._go_to_sleep_after(self._timeout))

    async def _go_to_sleep_after(self, secs: float) -> None:
        try:
            await asyncio.sleep(secs)
            self._awake = False
            self._model.reset()
            if self._probe is not None:
                self._probe.go_idle()
            logger.info("WakeWordGate: back to sleep")
        except asyncio.CancelledError:
            pass

    def notify_user_activity(self) -> None:
        """Hook for TranscriptWatcher: any user speech keeps the gate awake."""
        if self._awake:
            self._renew_keepalive()

    # -- pipeline ------------------------------------------------------------

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # Every non-audio frame (Start/End/Interruption/system) must always pass.
        if not isinstance(frame, InputAudioRawFrame):
            await self.push_frame(frame, direction)
            return

        # Reposo ("Descansa" por Telegram): se descarta el audio sin correr el modelo
        # -> wake-word a 0 CPU e imposible despertar por voz (se revive por Telegram).
        if REST.resting:
            if self._awake:                  # si estaba despierto al entrar en reposo, duérmelo
                self._awake = False
                self._model.reset()
                if self._probe is not None:
                    self._probe.go_idle()
            return

        if self._awake:
            await self.push_frame(frame, direction)
            return

        # Asleep: consume audio locally, never forward it.
        self._buffer.extend(frame.audio)
        while len(self._buffer) >= CHUNK_BYTES:
            chunk = bytes(self._buffer[:CHUNK_BYTES])
            del self._buffer[:CHUNK_BYTES]

            if time.monotonic() - self._last_wake < REARM_COOLDOWN_SECS:
                continue

            audio = np.frombuffer(chunk, dtype=np.int16)
            score = self._model.predict(audio).get(self._model_key, 0.0)
            if score >= self._threshold:
                self._awake = True
                self._last_wake = time.monotonic()
                self._buffer.clear()
                self._model.reset()
                self._renew_keepalive()
                if self._probe is not None:
                    self._probe.on_wake(score)
                logger.info(f"Wake word detected (score={score:.2f})")
                # TODO(Fase 1): optional audible ack — queue a short
                # TTSSpeakFrame("¿Sí?") via the task if it feels natural.
                break
