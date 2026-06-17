"""VoiceStateObserver — estado de voz en tiempo real -> /logs/voice_state.json.

Observer PASIVO de Pipecat 1.3.0. `on_push_frame()` recibe TODOS los frames en
TODOS los enlaces del pipeline y en ambas direcciones (FramePushed), así que
captura el ciclo completo idle->wake->listening->transcribing->thinking->
speaking->idle sin depender de la posición de un FrameProcessor (los frames de
STT/LLM viajan aguas abajo desde su origen, y un processor mal situado se los
perdería). Esa es la razón de usar un observer y no un processor.

Vuelca el estado de forma ATÓMICA (fichero .tmp + os.replace en el mismo fs) al
volumen compartido /logs (montado en orchestrator y panel), que el panel lee con
caducidad por mtime. Sin HTTP, sin SQLite. Throttled para no castigar el NVMe.

La señal de wake NO viaja como frame propio (WakeWordGate solo pone
self._awake=True); por eso el gate llama a observer.on_wake() directamente.

Nombres de frame verificados contra el contenedor (pipecat 1.3.0).
"""

import asyncio
import json
import os
import time
from pathlib import Path

import numpy as np
from loguru import logger

from pipecat.frames.frames import (
    InputAudioRawFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    TranscriptionFrame,
    InterimTranscriptionFrame,
    LLMFullResponseStartFrame,
    MetricsFrame,
    TTSTextFrame,
    FunctionCallInProgressFrame,
    FunctionCallResultFrame,
)
from pipecat.metrics.metrics import TTFBMetricsData, LLMUsageMetricsData
from pipecat.observers.base_observer import BaseObserver, FramePushed

# function_name -> etiqueta humana para el HUD ("¿qué hace Jarvis?")
_TOOL_LABELS = {
    "consultar_agenda": "Consultando tu agenda",
    "investigar": "Investigando a fondo (Claude Code)",
    "encargar": "Ejecutando una tarea (Claude Code)",
    "recordar": "Buscando en la memoria",
    "crear_recordatorio": "Anotando un recordatorio",
    "programar_tarea": "Programando una tarea",
    "listar_tareas": "Mirando tus tareas programadas",
    "cancelar_tarea": "Cancelando una tarea",
    "briefing_matutino": "Preparando el resumen del día",
    "web_search": "Buscando en internet",
    "web_read": "Leyendo una página",
    "ver_camara": "Mirando la cámara",
    "crear_recordatorio": "Creando un recordatorio",
    "confirmar_accion": "Confirmando la acción",
}

# processor de Pipecat -> etapa que mostramos en el HUD
def _stage_of(proc: str) -> str | None:
    p = (proc or "").lower()
    if "stt" in p or "whisper" in p or "parakeet" in p: return "stt"
    if "llm" in p or "openai" in p: return "llm"
    if "tts" in p or "piper" in p or "eleven" in p: return "tts"
    return None

STATE_PATH = Path(os.getenv("VOICE_STATE_PATH", "/logs/voice_state.json"))
_MIN_WRITE_INTERVAL = float(os.getenv("VOICE_STATE_MIN_INTERVAL", "0.15"))   # ~6 escrituras/s máx
_LEVEL_INTERVAL = float(os.getenv("VOICE_STATE_LEVEL_INTERVAL", "0.2"))      # nivel ~5/s
_HEARTBEAT = float(os.getenv("VOICE_STATE_HEARTBEAT", "2.5"))               # reescribe estado vivo

# Estados "activos": mientras persistan, un heartbeat refresca 'updated' para que
# el panel no los degrade por frescura aunque no haya transición (p.ej. TTS largo).
_ACTIVE = frozenset({"wake", "listening", "transcribing", "thinking", "tool", "speaking"})


class VoiceStateObserver(BaseObserver):
    def __init__(self, *, model: str = "", **kwargs):
        super().__init__(**kwargs)
        self._model = model
        self._state = "idle"
        self._since = time.time()
        self._last_wake = 0.0
        self._last_user_text = ""
        self._last_bot_text = ""
        self._bot_buf = ""                 # texto del bot acumulado (karaoke por TTSTextFrame)
        self._tool = ""                    # herramienta en uso (etiqueta humana)
        self._ttfb = {}                    # latencias por etapa: {"stt":s,"llm":s,"tts":s}
        self._level = 0.0
        self._last_write = 0.0
        self._last_level_calc = 0.0
        self._seen = None              # id() del último frame procesado (dedup multi-enlace)
        self._hb_task: asyncio.Task | None = None
        self._write(force=True)        # deja el fichero en disco al arrancar

    # -- API para el WakeWordGate (no hay frame de wake) ---------------------
    def on_wake(self, score: float = 0.0) -> None:
        """Lo llama WakeWordGate al detectar 'hey Jarvis'."""
        self._last_wake = time.time()
        self._set_state("wake", force=True)

    def go_idle(self) -> None:
        """Lo llama el gate al dormirse."""
        self._set_state("idle", force=True)

    # -- máquina de estados -------------------------------------------------
    def _set_state(self, state: str, *, force: bool = False) -> None:
        if state != self._state:
            self._state = state
            self._since = time.time()
            if state in ("idle", "wake", "listening"):
                self._level = 0.0
            self._write(force=True)
            self._arm_heartbeat()
        elif force:
            self._write(force=True)

    # -- heartbeat: reescribe mientras un estado activo persiste ------------
    def _arm_heartbeat(self) -> None:
        if self._hb_task and not self._hb_task.done():
            self._hb_task.cancel()
        if self._state in _ACTIVE:
            try:
                self._hb_task = asyncio.create_task(self._heartbeat_loop())
            except RuntimeError:
                self._hb_task = None   # sin loop (init): el siguiente set_state lo arma

    async def _heartbeat_loop(self) -> None:
        try:
            while self._state in _ACTIVE:
                await asyncio.sleep(_HEARTBEAT)
                self._write(force=True)   # refresca 'updated' aunque no cambie el estado
        except asyncio.CancelledError:
            pass

    # -- escritura atómica + throttle ---------------------------------------
    def _write(self, *, force: bool = False) -> None:
        now = time.time()
        if not force and (now - self._last_write) < _MIN_WRITE_INTERVAL:
            return
        self._last_write = now
        payload = {
            "state": self._state,
            "since": round(self._since, 3),
            "last_wake": round(self._last_wake, 3) if self._last_wake else None,
            "last_user_text": self._last_user_text,
            "last_bot_text": self._last_bot_text,
            "tool": self._tool,
            "ttfb": self._ttfb,
            "level": round(self._level, 3),
            "model": self._model,
            "updated": round(now, 3),
        }
        try:
            tmp = STATE_PATH.with_suffix(".json.tmp")     # mismo dir/fs => os.replace atómico
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, STATE_PATH)
        except Exception as e:
            logger.warning(f"voice_state write failed: {e}")

    # -- observer -----------------------------------------------------------
    async def on_push_frame(self, data: FramePushed) -> None:
        frame = data.frame
        fid = id(frame)
        # Un mismo frame se empuja por varios enlaces -> lo vemos N veces.
        # Para estados es idempotente; para nivel/no-repetir, dedup por id().
        dup = fid == self._seen
        self._seen = fid

        if isinstance(frame, InputAudioRawFrame):
            if not dup:
                self._update_level(frame)
            return
        if dup:
            return

        if isinstance(frame, UserStartedSpeakingFrame):
            self._set_state("listening")
        elif isinstance(frame, (TranscriptionFrame, InterimTranscriptionFrame)):
            txt = getattr(frame, "text", "")
            if txt:
                self._last_user_text = txt
            # no degradar si ya pensamos/hablamos (STT final tardío)
            if self._state in ("listening", "transcribing"):
                self._set_state("transcribing")
        elif isinstance(frame, UserStoppedSpeakingFrame):
            if self._state == "listening":
                self._set_state("transcribing")
        elif isinstance(frame, LLMFullResponseStartFrame):
            self._bot_buf = ""                 # nuevo turno: vacía el subtítulo del bot
            self._last_bot_text = ""
            self._set_state("thinking")
        elif isinstance(frame, BotStartedSpeakingFrame):
            self._set_state("speaking")
        elif isinstance(frame, TTSTextFrame):
            # karaoke: el texto aparece a medida que el TTS lo va diciendo
            piece = getattr(frame, "text", "") or ""
            if piece:
                sep = " " if self._bot_buf and not self._bot_buf.endswith(" ") else ""
                self._bot_buf = (self._bot_buf + sep + piece)[:300]
                self._last_bot_text = self._bot_buf
                self._write()                  # escritura suave (throttle)
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._set_state("idle")
        elif isinstance(frame, FunctionCallInProgressFrame):
            self._tool = _TOOL_LABELS.get(getattr(frame, "function_name", ""), "Usando una herramienta")
            self._set_state("tool", force=True)
        elif isinstance(frame, FunctionCallResultFrame):
            self._set_state("thinking")   # ya tiene el resultado; lo procesa para responder
        elif isinstance(frame, MetricsFrame):
            self._capture_ttfb(frame)

    def _update_level(self, frame: InputAudioRawFrame) -> None:
        # Solo medimos voz cuando estamos despiertos (en idle el gate consume el
        # audio antes de stt; aquí lo ignoramos para no medir ruido ambiente).
        if self._state == "idle":
            return
        now = time.time()
        if (now - self._last_level_calc) < _LEVEL_INTERVAL:
            return
        try:
            samples = np.frombuffer(frame.audio, dtype=np.int16)
            if samples.size == 0:
                return
            rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
            self._level = min(1.0, rms / 8000.0)   # ~8000 RMS ≈ voz normal -> 1.0
        except Exception:
            return
        self._last_level_calc = now
        self._write()   # nivel: escritura suave, respeta _MIN_WRITE_INTERVAL

    def _capture_ttfb(self, frame: MetricsFrame) -> None:
        """Time-to-first-byte por etapa (STT/LLM/TTS) desde las métricas de Pipecat."""
        changed = False
        for item in (getattr(frame, "data", None) or []):
            if isinstance(item, TTFBMetricsData):
                stage = _stage_of(getattr(item, "processor", ""))
                val = getattr(item, "value", None)
                if stage and isinstance(val, (int, float)) and val > 0:
                    self._ttfb[stage] = round(float(val), 2)
                    changed = True
            elif isinstance(item, LLMUsageMetricsData):
                self._log_usage(item)
        if changed:
            self._write()

    def _log_usage(self, item) -> None:
        """Registra el consumo de tokens del LLM (OpenCode Go) como evento, para el HUD."""
        u = getattr(item, "value", None)
        if u is None:
            return
        p = int(getattr(u, "prompt_tokens", 0) or 0)
        c = int(getattr(u, "completion_tokens", 0) or 0)
        cache = int(getattr(u, "cache_read_input_tokens", 0) or 0)
        if p == 0 and c == 0:
            return
        try:
            import events
            events.log_event("llm_usage", {"prompt": p, "completion": c, "cache": cache,
                                           "model": getattr(item, "model", "") or self._model})
        except Exception as e:
            logger.warning(f"llm_usage log failed: {e}")
