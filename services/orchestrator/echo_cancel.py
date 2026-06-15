"""AEC in-process con el APM de WebRTC (livekit-rtc) — PLAN_FINAL §5.2 plan C.

El micro (Yeti) capta el eco de los altavoces (Scarlett) y el VAD interrumpe al bot.
El AudioProcessingModule cancela ese eco usando como REFERENCIA el audio TTS que se
envia a la salida.

Arquitectura (todo a 16 kHz mono, que es el rate de entrada del micro):
  - EchoCanceller: posee el APM. process_capture() limpia el micro; feed_reference()
    recibe el TTS ya resampleado a 16 kHz. El APM de WebRTC es thread-safe entre el
    hilo de captura (process_stream) y el de render (process_reverse_stream): es su
    contrato de diseno, por eso no hace falta lock.
  - EchoCancelFilter: BaseAudioFilter que el transport de entrada aplica al micro
    ANTES del VAD y del wake word.
  - ReferenceTap: FrameProcessor que va justo antes de transport.output(); resamplea
    el TTS (22050) a 16 kHz y lo entrega como referencia.

WebRTC APM exige frames de exactamente 10 ms -> a 16 kHz mono = 160 samples = 320 bytes.
El retardo de ida y vuelta (salida USB + acustica + entrada) se le indica al APM con
set_stream_delay_ms (calibrable por env AEC_STREAM_DELAY_MS).
"""
from __future__ import annotations

import os

from livekit import rtc
from loguru import logger

from pipecat.audio.filters.base_audio_filter import BaseAudioFilter
from pipecat.audio.utils import create_stream_resampler
from pipecat.frames.frames import Frame, OutputAudioRawFrame, TTSAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

APM_RATE = 16000
FRAME_SAMPLES = APM_RATE // 100        # 160 samples = 10 ms
FRAME_BYTES = FRAME_SAMPLES * 2        # int16 mono


class EchoCanceller:
    """Envuelve el APM de WebRTC y bufferiza a frames de 10 ms."""

    def __init__(self, stream_delay_ms: int = 120):
        ns = os.getenv("AEC_NS", "true").lower() == "true"
        hpf = os.getenv("AEC_HPF", "true").lower() == "true"
        agc = os.getenv("AEC_AGC", "false").lower() == "true"
        self._apm = rtc.AudioProcessingModule(
            echo_cancellation=True,
            noise_suppression=ns,
            auto_gain_control=agc,
            high_pass_filter=hpf,
        )
        self._apm.set_stream_delay_ms(stream_delay_ms)
        self._cap_buf = bytearray()
        self._ref_buf = bytearray()
        logger.info(
            f"EchoCanceller listo (APM 16kHz, delay={stream_delay_ms}ms, ns={ns}, hpf={hpf}, agc={agc})"
        )

    def feed_reference(self, audio_16k: bytes) -> None:
        """Audio de salida (TTS) ya a 16 kHz mono -> process_reverse_stream en frames de 10 ms."""
        self._ref_buf.extend(audio_16k)
        while len(self._ref_buf) >= FRAME_BYTES:
            chunk = bytes(self._ref_buf[:FRAME_BYTES])
            del self._ref_buf[:FRAME_BYTES]
            try:
                self._apm.process_reverse_stream(
                    rtc.AudioFrame(chunk, APM_RATE, 1, FRAME_SAMPLES)
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"AEC reverse: {e}")

    def process_capture(self, audio_16k: bytes) -> bytes:
        """Micro a 16 kHz mono -> process_stream (in place) y devuelve audio limpio."""
        self._cap_buf.extend(audio_16k)
        out = bytearray()
        while len(self._cap_buf) >= FRAME_BYTES:
            chunk = bytes(self._cap_buf[:FRAME_BYTES])
            del self._cap_buf[:FRAME_BYTES]
            try:
                frame = rtc.AudioFrame(chunk, APM_RATE, 1, FRAME_SAMPLES)
                self._apm.process_stream(frame)
                out.extend(bytes(frame.data))
            except Exception as e:  # noqa: BLE001
                logger.warning(f"AEC capture: {e}")
                out.extend(chunk)
        return bytes(out)


class EchoCancelFilter(BaseAudioFilter):
    """Filtro de entrada: limpia el micro con el APM antes del VAD."""

    def __init__(self, canceller: EchoCanceller):
        self._ec = canceller
        self._enabled = os.getenv("AEC_BYPASS_CAPTURE", "false").lower() != "true"
        self._dump = os.getenv("AEC_DUMP") == "1"
        self._dumped = 0

    async def start(self, sample_rate: int) -> None:
        if sample_rate != APM_RATE:
            logger.warning(
                f"AEC: el transport entra a {sample_rate} Hz, el APM espera {APM_RATE}. "
                "Ajusta audio_in_sample_rate=16000."
            )

    async def stop(self) -> None:
        pass

    async def process_frame(self, frame) -> None:
        # Soporta FilterEnableFrame para activar/desactivar en caliente.
        enable = getattr(frame, "enable", None)
        if enable is not None:
            self._enabled = bool(enable)
            logger.info(f"AEC filtro {'activado' if self._enabled else 'desactivado'}")

    async def filter(self, audio: bytes) -> bytes:
        out = audio if not self._enabled else self._ec.process_capture(audio)
        if self._dump and self._dumped < 320000:  # ~10 s a 16 kHz
            try:
                with open("/logs/aec_in.raw", "ab") as f:
                    f.write(audio)
                with open("/logs/aec_out.raw", "ab") as f:
                    f.write(out)
                self._dumped += len(out)
            except Exception:  # noqa: BLE001
                pass
        return out


class ReferenceTap(FrameProcessor):
    """Va antes de transport.output(): pasa el TTS al APM como referencia (resampleado a 16k)."""

    def __init__(self, canceller: EchoCanceller, **kwargs):
        super().__init__(**kwargs)
        self._ec = canceller
        self._resampler = create_stream_resampler()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, (TTSAudioRawFrame, OutputAudioRawFrame)) and frame.audio:
            try:
                audio = frame.audio
                if frame.sample_rate != APM_RATE:
                    audio = await self._resampler.resample(
                        audio, frame.sample_rate, APM_RATE
                    )
                self._ec.feed_reference(audio)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"AEC tap: {e}")
        await self.push_frame(frame, direction)
