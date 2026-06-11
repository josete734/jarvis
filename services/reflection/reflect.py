"""Nightly reflection job (PLAN_FINAL §8; estudio §9.3). Run via systemd timer
at 04:00: `docker compose run --rm reflection`.

1. Collect today's conversation events from /logs/events.db.
2. Send them to jarvis-main with prompts/reflection_nightly.md.
3. Apply the result: new consolidated facts -> mem0 (origin=reflection);
   profile updates -> persona/perfil_usuario.md (git commit host-side).
4. Security review (§9.1, v2): quarantine suspicious new memories
   (imperative instructions, credentials, contradictions).

TODO(Fase 3): wire steps 3-4 once memory is enabled and transcripts flow
into events.db; today this runs end-to-end but only logs its proposal.
"""

import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from loguru import logger
from openai import OpenAI

EVENTS_DB = Path("/logs/events.db")
PROFILE = Path("/persona/perfil_usuario.md")
PROMPT = Path("/prompts/reflection_nightly.md")

client = OpenAI(
    base_url=os.getenv("LLM_BASE", "http://litellm:4000/v1"),
    api_key=os.getenv("LITELLM_API_KEY", "sk-litellm"),
)


def todays_transcript() -> str:
    if not EVENTS_DB.exists():
        return ""
    midnight = time.mktime(datetime.now().date().timetuple())
    conn = sqlite3.connect(EVENTS_DB)
    try:
        rows = conn.execute(
            "SELECT ts, kind, payload FROM events WHERE ts >= ? AND kind IN "
            "('user_said', 'assistant_said', 'presence') ORDER BY ts",
            (midnight,),
        ).fetchall()
    finally:
        conn.close()
    lines = []
    for ts, kind, payload in rows:
        stamp = datetime.fromtimestamp(ts).strftime("%H:%M")
        lines.append(f"[{stamp}] {kind}: {payload}")
    return "\n".join(lines)


def main() -> None:
    transcript = todays_transcript()
    if not transcript.strip():
        logger.info("No conversations today — nothing to reflect on")
        return

    prompt = PROMPT.read_text(encoding="utf-8")
    response = client.chat.completions.create(
        model="jarvis-main",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": transcript},
        ],
        temperature=0.3,
    )
    result = response.choices[0].message.content
    logger.info(f"Reflection output:\n{result}")

    # Append a dated section to the evolving profile (git diff = audit trail).
    today = datetime.now().strftime("%Y-%m-%d")
    with PROFILE.open("a", encoding="utf-8") as f:
        f.write(f"\n\n## Reflexión {today}\n\n{result}\n")
    logger.info(f"Profile updated: {PROFILE} (commit it host-side)")

    # TODO(Fase 3): parse the JSON sections of `result` and:
    #   - mem0.add(fact, metadata={"origin": "reflection"}) per consolidated fact
    #     (reuse build_local_config() from the orchestrator — duplicated here on
    #      purpose: separate build context)
    #   - quarantine list -> /logs/memory_quarantine.json for panel review


if __name__ == "__main__":
    main()
