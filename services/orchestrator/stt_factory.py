"""STT selection (PLAN_FINAL §3.4).

STT_BACKEND=whisper  -> faster-whisper in-process (v1; zero extra services)
STT_BACKEND=openai   -> any OpenAI-compatible STT server (Fase 2-3: parakeet
                        via the `stt-parakeet` compose profile). Switching back
                        is a one-line env change.
"""

import os

from loguru import logger


def build_stt():
    backend = os.getenv("STT_BACKEND", "whisper").lower()

    if backend == "openai":
        from pipecat.services.openai.stt import OpenAISTTService

        base_url = os.getenv("STT_BASE_URL", "http://stt-parakeet:8000/v1")
        logger.info(f"STT: OpenAI-compatible server at {base_url} (parakeet)")
        return OpenAISTTService(
            api_key="none",
            base_url=base_url,
            model="whisper-1",       # endpoint convention; server runs parakeet
        )

    from pipecat.services.whisper.stt import Model, WhisperSTTService

    name = os.getenv("WHISPER_MODEL", "small").lower()
    model = {
        "tiny": Model.TINY,
        "base": Model.BASE,
        "small": Model.SMALL,
        "medium": Model.MEDIUM,
        "large-v3": Model.LARGE_V3,
        "large-v3-turbo": Model.LARGE_V3_TURBO,
    }.get(name, Model.SMALL)

    logger.info(f"STT: faster-whisper {name} INT8 (CPU)")
    # TODO(Fase 1): confirm kwarg names for language/compute on 1.3.0
    # (research: device + compute_type supported; language fixes Spanish and
    # skips auto-detection).
    return WhisperSTTService(model=model, device="cpu", compute_type="int8", language="es")
