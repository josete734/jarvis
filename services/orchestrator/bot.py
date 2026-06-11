"""J.A.R.V.I.S. orchestrator — Pipecat 1.3.0 pipeline.

Pipeline (PLAN_FINAL §3.1, position verified against pipecat v1.3.0 source):

    transport.input() -> WakeWordGate -> STT -> TranscriptWatcher
        -> [memory] -> user_aggregator(VAD + smart-turn default) -> LLM
        -> TTS -> transport.output() -> assistant_aggregator

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
from pipecat.pipeline.task import PipelineTask
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
from pipecat.adapters.schemas.tools_schema import ToolsSchema

import events
from memory import build_memory_service
from security import SecurityState, TranscriptWatcher
from stt_factory import build_stt
from tools import register_tools
from wakeword_gate import WakeWordGate

PROMPTS = Path("/prompts")
PERSONA = Path("/persona")


def _env_int(name: str):
    val = os.getenv(name, "").strip()
    return int(val) if val else None


def load_system_prompt() -> str:
    """Compose system prompt: core rules + personality sheet + relationship state."""
    parts = []
    for path in (PROMPTS / "system_jarvis.md", PERSONA / "jarvis.md", PERSONA / "relacion.md"):
        if path.exists():
            parts.append(path.read_text(encoding="utf-8").strip())
    return "\n\n---\n\n".join(parts)


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

    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=16000,           # openwakeword + whisper expect 16 kHz
            audio_out_sample_rate=22050,          # davefx-medium native rate
            input_device_index=_env_int("AUDIO_INPUT_INDEX"),
            output_device_index=_env_int("AUDIO_OUTPUT_INDEX"),
        )
    )

    gate = WakeWordGate(
        model_path=os.getenv("WAKE_MODEL_PATH", "/models/openwakeword/hey_jarvis_v0.1.onnx"),
        threshold=float(os.getenv("WAKE_THRESHOLD", "0.5")),
        wake_timeout_secs=float(os.getenv("WAKE_TIMEOUT_SECS", "45")),
    )

    stt = build_stt()
    watcher = TranscriptWatcher(security)

    llm = OpenAILLMService(
        api_key=os.getenv("LITELLM_API_KEY", "sk-litellm"),
        base_url=os.getenv("LLM_BASE", "http://litellm:4000/v1"),
        model="jarvis-main",
    )

    # Firma verificada contra pipecat v1.3.0: el TTS embebido toma la voz vía
    # PiperTTSSettings (no kwarg `voice`) y reutiliza /models/piper (download_models.sh).
    tts = PiperTTSService(
        settings=PiperTTSSettings(voice=os.getenv("PIPER_VOICE", "es_ES-davefx-medium")),
        download_dir=Path("/models/piper"),
    )

    schemas = register_tools(llm, security)

    context = LLMContext(
        messages=[{"role": "system", "content": load_system_prompt()}],
        tools=ToolsSchema(standard_tools=schemas) if schemas else None,
    )
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
            # smart-turn v3.2 is the default stop strategy in 1.3.0 — do not disable.
        ),
    )

    processors = [transport.input(), gate, stt, watcher]

    memory = build_memory_service(security)        # None until MEM0_ENABLED=true (Fase 3)
    if memory:
        processors.append(memory)

    processors += [
        aggregators.user(),
        llm,
        tts,
        transport.output(),
        aggregators.assistant(),
    ]

    # Interrupciones (barge-in) activas por defecto en Pipecat 1.x; el control de fin
    # de turno va en LLMUserAggregatorParams (smart-turn), no en PipelineParams.
    task = PipelineTask(Pipeline(processors))

    # Internal HTTP server: presence events (Fase 5), DND toggle, event log.
    await events.start(task, security, port=int(os.getenv("EVENTS_PORT", "8070")))

    logger.info("Jarvis pipeline starting (say 'hey Jarvis')")
    await PipelineRunner().run(task)


if __name__ == "__main__":
    if "--list-devices" in sys.argv:
        list_audio_devices()
        sys.exit(0)
    asyncio.run(main())
