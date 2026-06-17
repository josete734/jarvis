"""Transcripción de notas de voz/audio de Telegram con faster-whisper.

Reutiliza el MISMO modelo Whisper que el pipeline de voz (WHISPER_MODEL, por
defecto "small"), ya cacheado en /models, así que no descarga nada. La carga es
perezosa (primer audio) y la transcripción corre en un hilo aparte para no
bloquear el bucle asyncio del agente de Telegram. faster-whisper decodifica el
OGG/Opus de Telegram directamente vía PyAV, sin necesidad de ffmpeg.
"""

import asyncio
import os

from loguru import logger

_MODEL = None


def _model():
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel
        size = os.getenv("WHISPER_MODEL", "small")
        _MODEL = WhisperModel(size, device="cpu", compute_type="int8", download_root="/models")
        logger.info(f"[voz-tg] WhisperModel cargado ({size}, int8)")
    return _MODEL


def _transcribe_sync(path: str) -> str:
    segments, _info = _model().transcribe(path, language="es", vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()


async def transcribe(path: str) -> str:
    """Transcribe el fichero de audio en un hilo; devuelve el texto (o '')."""
    return await asyncio.to_thread(_transcribe_sync, path)
