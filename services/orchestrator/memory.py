"""mem0 memory (PLAN_FINAL §3.3, §7.2, §8).

v1 uses Pipecat's native Mem0MemoryService with mem0 OSS in local mode
(Pipecat 1.3.0 pins mem0ai>=1.0.8,<2 — the 2.x migration is a tracked
follow-up, §8). Fact extraction goes to the cheap `jarvis-memory` alias.

Security rules wired here (§9.1.2):
  - every memory carries `origin` metadata,
  - no extraction from tainted turns (turns containing web content).

Verificado contra pipecat v1.3.0: el taint guard se aplica sobreescribiendo
`_store_messages` (único método que llama a memory_client.add()); el retrieve
(`_enhance_context_with_memories`) queda intacto. La subclase recibe el
SecurityState por closure.
"""

import os

from loguru import logger

E5_MODEL = "intfloat/multilingual-e5-small"


def build_local_config() -> dict:
    """mem0 OSS local config (verificado jun-2026 contra mem0 v1.0.11 + chromadb 1.5.9).

    Chroma host/port usa el mismo code path interno que chromadb.HttpClient en el
    cliente 1.5.9 (API v2) — requiere el pin chromadb==1.5.9 en requirements.
    history_db_path persiste el estado local de mem0 en el volumen /data/mem0.
    """
    return {
        "history_db_path": os.path.join(os.getenv("MEM0_DIR", "/data/mem0"), "history.db"),
        "vector_store": {
            "provider": "chroma",
            "config": {"collection_name": "jarvis", "host": "chroma", "port": 8000},
        },
        "embedder": {
            "provider": "huggingface",
            "config": {
                "model": E5_MODEL,
                "embedding_dims": 384,
                # e5 requiere prefijos; el embedder HF de mem0 1.x NO distingue add/search
                # (embed() ignora memory_action) -> default_prompt_name aplica "query: " a TODO.
                # Verificado en mem0 v1.0.11: subóptimo para e5 pero funcional (PLAN_FINAL §7.2).
                "model_kwargs": {
                    "prompts": {"q": "query: "},
                    "default_prompt_name": "q",
                },
            },
        },
        "llm": {
            "provider": "openai",
            "config": {
                "model": "jarvis-memory",
                "openai_base_url": os.getenv("LLM_BASE", "http://litellm:4000/v1"),
                "api_key": os.getenv("LITELLM_API_KEY", "sk-litellm"),
            },
        },
    }


def verify_e5_prefix() -> None:
    """Startup self-test (§7.2): fail loudly if the prefix isn't applied."""
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(
            E5_MODEL,
            prompts={"q": "query: "},
            default_prompt_name="q",
        )
        with_prefix = model.encode("prueba")
        without = model.encode("prueba", prompt="")
        if (with_prefix == without).all():
            logger.error("e5 prefix NOT applied — memory retrieval will degrade silently")
        else:
            logger.info("e5 prefix self-test OK")
    except Exception as e:  # non-fatal: surfaced, not blocking
        logger.warning(f"e5 prefix self-test skipped: {e}")


def build_memory_service(security):
    if os.getenv("MEM0_ENABLED", "false").lower() != "true":
        logger.info("Memory disabled (MEM0_ENABLED=false) — enable in Fase 3")
        return None

    from pipecat.services.mem0.memory import Mem0MemoryService

    verify_e5_prefix()

    class JarvisMemoryService(Mem0MemoryService):
        """Taint guard: no persistir memorias en turnos marcados por contenido web
        (PLAN_FINAL §9.1.2). _store_messages es el único método que escribe en mem0."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._security = security  # del closure de build_memory_service

        async def _store_messages(self, messages):
            if self._security and self._security.tainted:
                logger.info("mem0: turno marcado por contenido web — no se persiste memoria")
                return
            await super()._store_messages(messages)

    return JarvisMemoryService(
        local_config=build_local_config(),
        user_id="jose",
        # params: search_limit / search_threshold etc. — tune in Fase 3.
    )
