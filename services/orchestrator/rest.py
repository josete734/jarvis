"""Estado de 'reposo' (Descansa/Revive).

Cuando está activo: el wake-word deja de procesar audio (CPU a cero, no se puede
despertar por voz) y la pantalla del HUD se apaga. Singleton de proceso, compartido
entre `telegram_agent` (lo conmuta) y `wakeword_gate` (lo consulta), igual que
`proactive.PRESENCE`. Se persiste a /logs para que el panel pueda mostrarlo; en el
arranque del proceso se asume DESPIERTO (no se reaplica nada al host).
"""

import json
import time
from pathlib import Path

from loguru import logger

_STATE = Path("/logs/rest_state.json")


class RestState:
    def __init__(self) -> None:
        self.resting: bool = False
        self.since: float = 0.0

    def enter(self) -> None:
        self.resting = True
        self.since = time.time()
        self._save()
        logger.info("REST: en reposo (oídos y pantalla en pausa)")

    def exit(self) -> None:
        self.resting = False
        self.since = 0.0
        self._save()
        logger.info("REST: despierto")

    def _save(self) -> None:
        try:
            _STATE.write_text(
                json.dumps({"resting": self.resting, "since": self.since}),
                encoding="utf-8",
            )
        except Exception:
            pass


REST = RestState()
