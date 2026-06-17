"""TunedWhisperSTTService — faster-whisper con tuning REAL (rank 2 de la investigación).

PROBLEMA (Pipecat 1.3.0): `WhisperSTTService.run_stt` llama a
`self._model.transcribe(audio_float, language=language)` SIN más parámetros, así que
pasar `initial_prompt`, `beam_size`, `condition_on_previous_text`, etc. al constructor
es un NO-OP (parece que afinas pero no cambia nada). Verificado contra el código del
contenedor (faster-whisper 1.2.1).

SOLUCIÓN: esta subclase
  1. añade `cpu_threads`/`num_workers` al WhisperModel (en `_load`), y
  2. ENVUELVE `self._model.transcribe` para inyectar los `transcribe_opts` de tuning,
     conservando intacto el `language` que pasa el padre (no tocamos esa ruta, que ya
     funciona). Así el tuning surte efecto sin reimplementar `run_stt` (robusto entre
     versiones).
"""

import os
import numpy as np
from loguru import logger

from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.services.settings import assert_given


class TunedWhisperSTTService(WhisperSTTService):
    def __init__(self, *args, transcribe_opts=None, cpu_threads=0, num_workers=1, **kwargs):
        # Asignar ANTES de super().__init__: la base (SegmentedSTTService) puede llamar a
        # _load() durante su init, que usa estos atributos -> si no, AttributeError.
        self._tw_opts = dict(transcribe_opts or {})
        self._tw_threads = int(cpu_threads)
        self._tw_workers = int(num_workers)
        super().__init__(*args, **kwargs)

    def _load(self):
        from faster_whisper import WhisperModel

        model_name = assert_given(self._settings.model)
        logger.info(
            f"TunedWhisper: cargando {model_name} cpu_threads={self._tw_threads} "
            f"opts={sorted(self._tw_opts)}"
        )
        self._model = WhisperModel(
            model_name,
            device=self._device,
            compute_type=self._compute_type,
            cpu_threads=self._tw_threads,
            num_workers=self._tw_workers,
        )

        # Inyecta el tuning en cada transcribe sin tocar la ruta de `language` del padre.
        _orig = self._model.transcribe
        opts = self._tw_opts

        max_turn = float(os.getenv("MAX_TURN_SECS", "8"))

        def _wrapped(audio, **kw):
            # Instrumentación + tope duro: el segmento debería ser ~la orden (~4s), no ~20s.
            dur = len(audio) / 16000.0
            if dur > max_turn:
                audio = audio[-int(max_turn * 16000):]
                logger.info(f"[stt] segmento {dur:.1f}s -> recortado a {max_turn:.0f}s")
            else:
                logger.info(f"[stt] segmento {dur:.1f}s")
            merged = {**opts, **kw}  # kw (language del padre) se conserva; opts añade tuning
            return _orig(audio, **merged)

        self._model.transcribe = _wrapped

        # Warm-up: evita el coste de la 1ª inferencia (~9s en frío) en producción.
        try:
            self._model.transcribe(np.zeros(16000, dtype=np.float32), language="es")
            logger.info("TunedWhisper: warm-up OK")
        except Exception as e:  # no fatal
            logger.warning(f"TunedWhisper: warm-up saltado: {e}")
