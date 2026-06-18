"""Selección de motor TTS (frente "voz" de la hoja de ruta).

TTS_BACKEND=elevenlabs -> ElevenLabs Flash v2.5: voz de mayordomo es-ES, baja
                          latencia (websocket), en la nube. Voz por defecto:
                          'Marco - Premium Spanish' (peninsular, grave).
TTS_BACKEND=piper (o si falta ELEVENLABS_API_KEY / falla la nube) -> Piper local
                          (es_ES-davefx-medium): respaldo OFFLINE, sin internet.

Allowlist FIJA en código (no en datos que un agente pueda tocar): solo 'elevenlabs'
y 'piper'. Si ElevenLabs no está disponible, cae a Piper sin dejar a Jarvis mudo.
"""
import os
from pathlib import Path

from loguru import logger

from pipecat.services.piper.tts import PiperTTSService, PiperTTSSettings


def _piper():
    voice = os.getenv("PIPER_VOICE", "es_ES-davefx-medium")
    logger.info(f"TTS: Piper local ({voice})")
    return PiperTTSService(
        settings=PiperTTSSettings(voice=voice),
        download_dir=Path("/models/piper"),
    )


def build_tts(sample_rate: int = 24000):
    backend = os.getenv("TTS_BACKEND", "piper").strip().lower()

    if backend == "elevenlabs" and os.getenv("ELEVENLABS_API_KEY", "").strip():
        try:
            from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
            from pipecat.transcriptions.language import Language

            voice = os.getenv("ELEVENLABS_VOICE_ID", "woeaOojf4khJahry1fqM")  # Marco
            logger.info(f"TTS: ElevenLabs flash v2.5 (voice={voice}, {sample_rate} Hz)")
            return ElevenLabsTTSService(
                api_key=os.environ["ELEVENLABS_API_KEY"],
                voice_id=voice,
                model=os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5"),
                sample_rate=sample_rate,
                params=ElevenLabsTTSService.InputParams(
                    language=Language.ES,
                    # mayordomo sereno: estabilidad media-alta, buen parecido, ritmo natural
                    stability=float(os.getenv("ELEVENLABS_STABILITY", "0.5")),
                    similarity_boost=float(os.getenv("ELEVENLABS_SIMILARITY", "0.8")),
                    speed=float(os.getenv("ELEVENLABS_SPEED", "1.0")),
                ),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"TTS: ElevenLabs no disponible ({e}); fallback a Piper local")

    return _piper()
