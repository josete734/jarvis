"""J.A.R.V.I.S. orchestrator — Pipecat 1.3.0 pipeline.

Pipeline (PLAN_FINAL §3.1, position verified against pipecat v1.3.0 source):

    transport.input() -> WakeWordGate -> STT -> TranscriptWatcher
        -> [memory] -> user_aggregator(VAD + smart-turn default) -> LLM
        -> ConversationLog -> TTS -> transport.output() -> assistant_aggregator

Smart-turn v3.2 (bundled, CPU, Spanish) is the DEFAULT stop strategy in 1.3.0:
we keep stop_secs=0.2 and let the model decide end-of-turn.

TODO(Fase 1): import paths below follow docs/source of pipecat 1.3.0 as
researched (jun-2026); adjust on first run if the package layout differs.
"""

import asyncio
import os
import sys
from pathlib import Path

from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.piper.tts import PiperTTSService, PiperTTSSettings
from pipecat.transports.local.audio import (
    LocalAudioTransport,
    LocalAudioTransportParams,
)

# TODO(Fase 1): universal context (pipecat 1.x). If these paths moved, see
# https://docs.pipecat.ai/pipecat/migration/migration-1.0
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.turns.user_mute.always_user_mute_strategy import AlwaysUserMuteStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.turns.user_start import VADUserTurnStartStrategy
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import Frame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from datetime import datetime

import events
from conversation_log import ConversationLog
from memory import build_memory_service
from security import SecurityState, TranscriptWatcher
from stt_factory import build_stt
from tools import register_tools
from wakeword_gate import WakeWordGate
from voice_state import VoiceStateObserver
from echo_cancel import EchoCanceller, EchoCancelFilter, ReferenceTap
from tts_factory import build_tts

PROMPTS = Path("/prompts")
PERSONA = Path("/persona")

_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre"]


def _momento_actual() -> str:
    """Bloque de fecha/hora real (del sistema) para inyectar en el system prompt."""
    n = datetime.now()
    return (
        "\n\n## Momento actual (dato del sistema, para tu referencia; NO lo inventes ni lo busques)\n"
        f"Ahora mismo es {_DIAS[n.weekday()]} {n.day} de {_MESES[n.month - 1]} de {n.year}, "
        f"las {n.hour:02d}:{n.minute:02d} (hora local de España). "
        "Úsalo solo si te preguntan EXPRESAMENTE la hora o la fecha. "
        "Si la pregunta es elíptica o un seguimiento (p.ej. «¿y mañana?», «¿y el viernes?»), "
        "NO contestes la fecha: continúa el tema anterior (si hablabais de la agenda, mira la agenda)."
    )


class TimeInjector(FrameProcessor):
    """Refresca la fecha/hora REAL en el system prompt en cada turno del usuario.

    Bug previo: el LLM se inventaba la hora porque nunca la recibía. Se dispara al
    transcribir (TranscriptionFrame), justo antes de que el agregador llame al LLM.
    """

    def __init__(self, context, base_system: str):
        super().__init__()
        self._ctx = context
        self._base = base_system
        self._turns = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            self._turns += 1
            if self._turns % 8 == 0:               # recarga aprendido.md/perfil en vivo (aprende sin reiniciar)
                try:
                    self._base = load_system_prompt()
                    self._ctx.messages[0]["content"] = self._base   # persona estable salvo recarga
                except Exception:
                    pass
            self._ctx.messages[1]["content"] = _momento_actual()    # solo se refresca el reloj (no rompe la caché de la persona)
        await self.push_frame(frame, direction)


def _env_int(name: str):
    val = os.getenv(name, "").strip()
    return int(val) if val else None


def _audio_index(env_name: str, fallback_name: str = "default"):
    """Índice de dispositivo de audio para PyAudio, robusto ante reordenado.

    Los índices de PyAudio NO son estables entre reinicios / replug del USB (el
    orden de tarjetas ALSA cambia). Por eso: si la env trae un entero se usa tal
    cual; si está vacía se busca POR NOMBRE el primer dispositivo que contenga
    `fallback_name` (por defecto "default" = el PCM asimétrico del asound.conf,
    que enruta captura->PIXY y reproducción->jack con remuestreo). Devuelve None
    si no se encuentra (PyAudio caería al default del sistema)."""
    val = os.getenv(env_name, "").strip()
    if val:
        return int(val)
    import pyaudio

    pa = pyaudio.PyAudio()
    try:
        for i in range(pa.get_device_count()):
            if fallback_name.lower() in pa.get_device_info_by_index(i)["name"].lower():
                logger.info(f"audio: {env_name} -> índice {i} (match '{fallback_name}')")
                return i
    finally:
        pa.terminate()
    logger.warning(f"audio: ningún dispositivo '{fallback_name}' para {env_name}; uso default de PyAudio")
    return None


def load_system_prompt() -> str:
    """System prompt de VOZ. La composición real (compartida con el canal de texto
    de Telegram) vive en sysprompt.compose() — una sola fuente de verdad."""
    import sysprompt
    return sysprompt.compose("voz")


def list_audio_devices() -> None:
    import pyaudio

    pa = pyaudio.PyAudio()
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        print(
            f"[{i}] {info['name']}  in={info['maxInputChannels']} "
            f"out={info['maxOutputChannels']}  rate={int(info['defaultSampleRate'])}"
        )
    pa.terminate()


async def main() -> None:
    security = SecurityState()

    # AEC software (livekit APM): solo cuando el hardware NO cancela el eco (p.ej.
    # micro+altavoz separados). Con el Anker PowerConf (USB o BT) la AEC es por
    # hardware -> SW_AEC=false. Conmutar SW_AEC/DISABLE_BARGE_IN según el dispositivo
    # (futuro: seleccionable desde el panel).
    # Rate de salida: ElevenLabs Flash rinde a 24 kHz; Piper (davefx) a 22050 y el
    # transport remuestrea. Único valor para el transport y para el TTS.
    audio_out_rate = int(os.getenv("AUDIO_OUT_RATE", "24000"))
    sw_aec = os.getenv("SW_AEC", "false").lower() == "true"
    aec = EchoCanceller(stream_delay_ms=int(os.getenv("AEC_STREAM_DELAY_MS", "120"))) if sw_aec else None
    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=16000,           # openwakeword + whisper expect 16 kHz
            audio_out_sample_rate=audio_out_rate,  # ElevenLabs 24k / Piper 22050 (remuestrea)
            audio_in_filter=EchoCancelFilter(aec) if aec else None,  # AEC SW: limpia el micro antes del VAD
            input_device_index=_audio_index("AUDIO_INPUT_INDEX", "jarvisin"),
            output_device_index=_audio_index("AUDIO_OUTPUT_INDEX", "jarvisout"),
        )
    )

    # Observer pasivo: refleja el estado real del pipeline en /logs/voice_state.json
    # para el HUD (lo lee el panel). No altera el audio ni el pipeline.
    voice_probe = VoiceStateObserver(model=os.getenv("WHISPER_MODEL", "small"))

    gate = WakeWordGate(
        model_path=os.getenv("WAKE_MODEL_PATH", "/models/openwakeword/hey_jarvis_v0.1.onnx"),
        threshold=float(os.getenv("WAKE_THRESHOLD", "0.5")),
        wake_timeout_secs=float(os.getenv("WAKE_TIMEOUT_SECS", "45")),
        probe=voice_probe,
    )

    stt = build_stt()
    watcher = TranscriptWatcher(security, gate=gate)   # renueva el keepalive del gate al hablar

    llm = OpenAILLMService(
        api_key=os.getenv("LITELLM_API_KEY", "sk-litellm"),
        base_url=os.getenv("LLM_BASE", "http://litellm:4000/v1"),
        model="jarvis-main",
        params=OpenAILLMService.InputParams(
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.5")),
            # Red de seguridad anti-divagación (la brevedad real la da el prompt):
            # ~160 tokens ≈ 2-3 frases en castellano. Tope holgado, NO tijera.
            # drop_params=true en LiteLLM tolera que un fallback no soporte el param.
            max_completion_tokens=int(os.getenv("LLM_MAX_TOKENS", "160")),
        ),
    )

    # TTS seleccionable (tts_factory): ElevenLabs Flash v2.5 (voz mayordomo es-ES) con
    # Piper local de respaldo offline. Conmutable por env TTS_BACKEND.
    tts = build_tts(audio_out_rate)

    schemas = register_tools(llm, security)

    base_system = load_system_prompt()
    # Persona ESTABLE en messages[0] (prefijo cacheable; no cambia turno a turno) y la
    # hora volátil en messages[1] -> la caché del prompt no se invalida por el reloj.
    context = LLMContext(
        messages=[{"role": "system", "content": base_system},
                  {"role": "system", "content": _momento_actual()}],
        tools=ToolsSchema(standard_tools=schemas) if schemas else None,
    )
    # Endpointing SEMÁNTICO: el VAD (stop_secs bajo) solo DISPARA la evaluación; smart-turn v3
    # (modelo de audio, ~12 ms CPU, español, incluido en el paquete) decide si de verdad
    # terminaste de hablar o haces una pausa para pensar -> recorta la espera fija de cada
    # respuesta sin cortarte. SMART_TURN_MAX_SECS es el techo de espera.
    _smart_turn = LocalSmartTurnAnalyzerV3(
        params=SmartTurnParams(stop_secs=float(os.getenv("SMART_TURN_MAX_SECS", "2.5"))))
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=float(os.getenv("VAD_STOP_SECS", "0.25")))),  # solo dispara; smart-turn confirma el fin de turno real
            user_turn_strategies=UserTurnStrategies(
                start=[VADUserTurnStartStrategy()],
                stop=[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=_smart_turn)],
            ),
            # DISABLE_BARGE_IN=true silencia al usuario mientras el bot habla (sin AEC HW).
            # Con el Anker (AEC hardware) barge-in activo -> se le puede cortar hablando.
            user_mute_strategies=(
                [AlwaysUserMuteStrategy()]
                if os.getenv("DISABLE_BARGE_IN", "false").lower() == "true"
                else []
            ),
        ),
    )

    processors = [transport.input(), gate, stt, watcher, TimeInjector(context, base_system)]

    memory = build_memory_service(security)        # None until MEM0_ENABLED=true (Fase 3)
    if memory:
        processors.append(memory)

    processors += [
        aggregators.user(),
        llm,
        # Vuelca 'assistant_said' a events.db para la reflexión nocturna
        # (acumula LLMTextFrame entre LLMFullResponseStart/EndFrame).
        ConversationLog(),
        tts,
        *([ReferenceTap(aec)] if aec else []),  # AEC SW: TTS -> referencia del APM
        transport.output(),
        aggregators.assistant(),
    ]

    # Interrupciones (barge-in) activas por defecto en Pipecat 1.x; el control de fin
    # de turno va en LLMUserAggregatorParams (smart-turn), no en PipelineParams.
    #
    # idle_timeout_secs=None: el WakeWordGate consume el audio mientras duerme, así
    # que sin "hey Jarvis" no fluye ningún frame y el watchdog de Pipecat (idle 300 s,
    # resetea con Bot/UserSpeakingFrame) cancelaría el worker -> reinicio cada 5 min.
    # Un asistente always-on idlea por diseño: desactivamos el idle timeout.
    task = PipelineTask(
        Pipeline(processors),
        # Métricas: mide TTFB de STT/LLM/TTS para optimizar latencia con datos reales.
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=None,
    )

    task.add_observer(voice_probe)   # estado de voz en vivo -> /logs/voice_state.json (HUD)

    # Internal HTTP server: presence events (Fase 5), DND toggle, event log.
    await events.start(task, security, port=int(os.getenv("EVENTS_PORT", "8070")))

    # Proactividad: heartbeat (recordatorios + agenda inminente) por el gate único.
    from proactive import ProactiveGate, Heartbeat
    proactive_gate = ProactiveGate(task, security)
    events.set_gate(proactive_gate)                 # Fase B: /event/* enruta por presencia
    asyncio.create_task(Heartbeat(proactive_gate).run())

    # Cron en lenguaje natural (Bloque 3): tareas recurrentes -> aviso por el gate.
    from cron import Cron
    asyncio.create_task(Cron(proactive_gate).run())

    # Curator: Jarvis aprende solo de las conversaciones -> /logs/aprendido.md
    from curator import Curator
    asyncio.create_task(Curator().run())

    # Agente de texto bidireccional por Telegram (Fase A): mismo cerebro+tools+memoria.
    from telegram_agent import TelegramAgent
    asyncio.create_task(TelegramAgent().run())

    logger.info("Jarvis pipeline starting (say 'hey Jarvis')")
    await PipelineRunner().run(task)


if __name__ == "__main__":
    if "--list-devices" in sys.argv:
        list_audio_devices()
        sys.exit(0)
    asyncio.run(main())
