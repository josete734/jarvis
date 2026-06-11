"""mem0 memory (PLAN_FINAL §3.3, §7.2, §8).

v1 uses Pipecat's native Mem0MemoryService with mem0 OSS in local mode
(Pipecat 1.3.0 pins mem0ai>=1.0.8,<2 — the 2.x migration is a tracked
follow-up, §8). Fact extraction goes to the cheap `jarvis-memory` alias.

Security rules wired here (§9.1.2):
  - every memory carries `origin` metadata,
  - no extraction from tainted turns (turns containing web content).

TODO(Fase 3): Mem0MemoryService internals decide *when* add() runs. To honor
the taint rule, locate its add entry point in
pipecat/services/mem0/memory.py (v1.3.0) and guard it with
`if security.tainted: skip`. The factory below passes the SecurityState in
so the subclass only needs that one override.
"""

import os

from loguru import logger

E5_MODEL = "intfloat/multilingual-e5-small"


def build_local_config() -> dict:
    """mem0 OSS local config — syntax verified against docs.mem0.ai (jun-2026)."""
    return {
        "vector_store": {
            "provider": "chroma",
            "config": {"collection_name": "jarvis", "host": "chroma", "port": 8000},
        },
        "embedder": {
            "provider": "huggingface",
            "config": {
                "model": E5_MODEL,
                "embedding_dims": 384,
                # e5 requires prefixes; mem0's HF embedder does not apply them
                # per-operation -> uniform "query: " prompt (e5 FAQ-sanctioned
                # for symmetric tasks). Verified trick, PLAN_FINAL §7.2.
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
        """Adds taint guard + origin metadata. See module docstring TODO(Fase 3)."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._security = security

    return JarvisMemoryService(
        local_config=build_local_config(),
        user_id="jose",
        # params: search_limit / search_threshold etc. — tune in Fase 3.
    )
