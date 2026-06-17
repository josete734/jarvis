"""Proactividad de Jarvis — heartbeat + GATE único (inspirado en OpenClaw/Hermes).

- ProactiveGate: la ÚNICA puerta de voz NO solicitada. Aplica DND, horas de
  silencio, presupuesto (máx N/hora) y dedup. TODO lo proactivo pasa por aquí
  ("una primitiva, no seis").
- Heartbeat: bucle que cada 60 s revisa recordatorios vencidos y eventos de
  agenda inminentes, y avisa por voz a través del gate.
- Recordatorios: fichero JSON en /logs (lo escribe la tool crear_recordatorio,
  lo lee el heartbeat).
"""

import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path

import aiohttp
from loguru import logger

from pipecat.frames.frames import TTSSpeakFrame

REMINDERS = Path("/logs/reminders.json")
PANEL = os.getenv("PANEL_INTERNAL", "http://panel:8080")
_DIAS_REV = {0: "lunes", 1: "martes", 2: "miércoles", 3: "jueves",
             4: "viernes", 5: "sábado", 6: "domingo"}
QUIET_START = int(os.getenv("PROACTIVE_QUIET_START", "22"))   # silencio 22:00…
QUIET_END = int(os.getenv("PROACTIVE_QUIET_END", "8"))        # …hasta 08:00
BUDGET_HOUR = int(os.getenv("PROACTIVE_BUDGET", "6"))         # máx avisos/hora
BRAIN_EVERY = int(os.getenv("PROACTIVE_BRAIN_MIN", "40"))     # revisión con cerebro cada ~40 min
LLM = os.getenv("LLM_BASE", "http://litellm:4000/v1")
LLM_KEY = os.getenv("LITELLM_API_KEY", "sk-litellm")

# --- presencia (Fase B) -----------------------------------------------------
# El orquestador es el dueño del estado presente/ausente; el servicio vision es
# solo un sensor que "late". Mientras NO haya cámara latiendo, se asume PRESENTE
# (fail-safe: comportamiento idéntico al actual, Jarvis nunca se queda mudo).
PRESENCE_TTL = int(os.getenv("PRESENCE_TTL", "45"))          # visto hace <45s = presente
VISION_STALE = int(os.getenv("VISION_STALE", "120"))        # sin latido >120s = vision caída
GREET_COOLDOWN = int(os.getenv("PRESENCE_GREET_COOLDOWN", "1800"))  # no saludar más de 1/30min
ECHO_TO_TELEGRAM = os.getenv("PROACTIVE_ECHO_TELEGRAM", "false").lower() == "true"
# Si José escribe por Telegram es porque NO está delante: durante esta ventana se le
# considera REMOTO -> todo lo proactivo va a Telegram, nunca por voz (a una casa vacía).
REMOTE_WINDOW = int(os.getenv("PRESENCE_REMOTE_WINDOW", "900"))     # 15 min desde el último Telegram


class PresenceState:
    """Estado vivo de presencia. `is_present` con fail-safe: sin sensor vivo, presente."""

    def __init__(self):
        self.last_seen: dict[str, float] = {}    # person -> ts visto por última vez
        self.last_beat: float = 0.0              # último POST de vision (cualquiera)
        self.last_greeted: dict[str, float] = {}
        self.last_remote_ts: float = 0.0         # último mensaje por Telegram (= está fuera)

    def beat(self, person: str | None = None) -> None:
        now = time.time()
        self.last_beat = now
        if person:
            self.last_seen[person] = now

    def mark_remote(self) -> None:
        """Llamado al recibir un mensaje de Telegram: José no está delante."""
        self.last_remote_ts = time.time()

    def is_remote(self) -> bool:
        return (time.time() - self.last_remote_ts) < REMOTE_WINDOW

    def vision_alive(self) -> bool:
        return (time.time() - self.last_beat) < VISION_STALE

    def is_present(self, person: str = "jose") -> bool:
        if self.is_remote():
            return False                         # acaba de escribir por Telegram -> NO está delante
        if not self.vision_alive():
            return True                          # FAIL-SAFE: sin cámara, asume presente
        return (time.time() - self.last_seen.get(person, 0)) < PRESENCE_TTL


PRESENCE = PresenceState()                       # singleton compartido (gate + events)


async def _llm(prompt: str) -> str:
    body = {"model": "jarvis-main", "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 120, "extra_body": {"reasoning_effort": "none"}}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{LLM}/chat/completions", json=body,
                              headers={"Authorization": "Bearer " + LLM_KEY},
                              timeout=aiohttp.ClientTimeout(total=30)) as r:
                j = await r.json()
        return (j["choices"][0]["message"].get("content") or "").strip()
    except Exception:
        return ""


# --- recordatorios (compartidos con la tool vía fichero) -------------------
def load_reminders() -> list:
    try:
        return json.loads(REMINDERS.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_reminders(r: list) -> None:
    try:
        tmp = REMINDERS.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, REMINDERS)
    except Exception as e:
        logger.warning(f"reminders save: {e}")


def add_reminder(text: str, due_ts: float) -> None:
    r = load_reminders()
    r.append({"id": str(int(time.time() * 1000)), "text": text,
              "due": float(due_ts), "done": False})
    save_reminders(r)


class ProactiveGate:
    """Puerta única de voz proactiva: DND + horas de silencio + presupuesto + dedup."""

    def __init__(self, task, security):
        self._task = task
        self._sec = security
        self._spoken: list[float] = []     # ts de avisos recientes (presupuesto)
        self._recent: dict[str, float] = {}  # key -> ts (dedup)

    def _quiet_now(self) -> bool:
        h = datetime.now().hour
        if QUIET_START <= QUIET_END:
            return QUIET_START <= h < QUIET_END
        return h >= QUIET_START or h < QUIET_END        # cruza medianoche

    async def say(self, text: str, *, key: str | None = None, force: bool = False,
                  tier: str = "info", person: str = "jose") -> bool:
        """Puerta única de voz proactiva con routing por presencia (Fase B).

        tier: 'ambient' (charla/sugerencia, lo más prescindible) | 'info' (agenda,
        investigaciones) | 'critical' (recordatorio que pidió José; salta presupuesto).
        force=True se mantiene por compatibilidad y equivale a tier='critical'.

        Matriz (presente × silencio/DND × tier → canal):
        - PRESENTE y sin silencio/DND: VOZ (critical además Telegram; info opcional con ECHO).
        - AUSENTE: nunca voz (no se habla a una casa vacía) -> Telegram (ambient: nada).
        - SILENCIO/DND: nada de voz -> Telegram silencioso (ambient: nada).
        """
        if force:
            tier = "critical"
        now = time.time()
        present = PRESENCE.is_present(person)
        quiet = self._quiet_now()
        dnd = getattr(self._sec, "dnd", False)

        if key and now - self._recent.get(key, 0) < 1800:   # dedup 30 min (todos los tiers)
            return False
        if tier != "critical":                              # presupuesto (critical lo salta)
            self._spoken = [t for t in self._spoken if now - t < 3600]
            if len(self._spoken) >= BUDGET_HOUR:
                return False

        voice = present and not quiet and not dnd
        if tier == "ambient":
            telegram_ok = False                              # la charla nunca va al móvil
        elif tier == "critical":
            telegram_ok = True                               # siempre llega (silencioso de noche)
        else:                                                # info
            telegram_ok = (not present) or quiet or dnd or ECHO_TO_TELEGRAM
        if not voice and not telegram_ok:
            return False                                     # casa vacía + ambient = silencio

        spoke = sent = False
        if voice:
            await self._task.queue_frames([TTSSpeakFrame(text)])
            spoke = True
        if telegram_ok:
            try:
                import telegram
                sent = await telegram.send(text, silent=(quiet or dnd))
            except Exception:
                pass
        if not spoke and not sent:
            return False

        self._spoken.append(now)
        if key:
            self._recent[key] = now
        try:
            import events
            events.log_event("proactive", {"text": text[:200], "key": key, "tier": tier,
                                           "via": ("voz" if spoke else "") + ("+tg" if sent else "")})
        except Exception:
            pass
        logger.info(f"[proactive] {tier} -> {'voz' if spoke else ''}{'+tg' if sent else ''}: {text[:50]}…")
        return True


class Heartbeat:
    """Latido proactivo: cada 60 s revisa recordatorios y agenda inminente."""

    def __init__(self, gate: ProactiveGate):
        self._gate = gate
        self._n = 0

    async def run(self) -> None:
        await asyncio.sleep(30)            # deja arrancar el pipeline
        logger.info("[proactive] heartbeat en marcha")
        while True:
            try:
                await self._tick()
                self._n += 1
                if self._n % BRAIN_EVERY == 0:   # revisión con cerebro de vez en cuando
                    await self._brain_review()
            except Exception as e:
                logger.warning(f"heartbeat tick: {e}")
            await asyncio.sleep(60)

    async def _brain_review(self) -> None:
        """OpenClaw-style: el cerebro mira el día + lo aprendido y decide si anticiparse."""
        if self._gate._quiet_now() or getattr(self._gate._sec, "dnd", False):
            return                       # en silencio/DND ni gastamos la llamada
        now = datetime.now()
        evs = []
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{PANEL}/api/agenda",
                                 timeout=aiohttp.ClientTimeout(total=6)) as r:
                    evs = (await r.json()).get("eventos", [])
        except Exception:
            pass
        hoy = [f"{e.get('cuando','')} {e.get('titulo','')}" for e in evs if "hoy" in (e.get("cuando", "").lower())]
        try:
            facts = Path("/logs/aprendido.md").read_text(encoding="utf-8")[:1500]
        except Exception:
            facts = "(aún no sé gran cosa de él)"
        ctx = (f"Es {_DIAS_REV.get(now.weekday(),'')} a las {now.hour:02d}:{now.minute:02d}. "
               f"Agenda de hoy que queda: {hoy or 'nada'}.\nLo que sabes de José:\n{facts}")
        prompt = (
            "Eres Jarvis, un mayordomo MUY discreto. Por defecto NO molestas. Responde solo la palabra "
            "SILENCIO salvo que haya algo verdaderamente OPORTUNO y CONCRETO que decirle a José AHORA: un "
            "evento inminente que conviene recordarle, o algo que acaba de hacerse relevante y le ahorra un "
            "problema real. NO hagas conversación, NO saques sus aficiones ni temas porque sí, NO sugieras "
            "cosas genéricas. Ante la mínima duda, SILENCIO. Si de verdad procede, UNA frase breve de "
            "mayordomo tratándole de señor.\n\n" + ctx)
        out = await _llm(prompt)
        if out and "SILENCIO" not in out.upper() and len(out) > 10:
            await self._gate.say(out.strip(), key="brain:" + now.strftime("%Y%m%d%H"),
                                 tier="ambient")

    async def _tick(self) -> None:
        now = time.time()
        # 1) recordatorios vencidos
        r = load_reminders()
        changed = False
        for rem in r:
            if not rem.get("done") and rem.get("due", 0) <= now:
                ok = await self._gate.say(
                    f"Señor, me pidió recordarle: {rem['text']}.",
                    key="rem:" + rem["id"], force=True,    # los recordatorios saltan el presupuesto/silencio
                )
                if ok:
                    rem["done"] = True
                    changed = True
        if changed:
            save_reminders(r)
        # 2) eventos de agenda que empiezan en ~10 min
        evs = []
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{PANEL}/api/agenda",
                                 timeout=aiohttp.ClientTimeout(total=6)) as resp:
                    evs = (await resp.json()).get("eventos", [])
        except Exception:
            pass
        for e in evs:
            st = e.get("start")
            if not st:
                continue
            mins = (st - now) / 60.0
            if 0 < mins <= 10:
                await self._gate.say(
                    f"Señor, en unos minutos tiene: {e['titulo']}.",
                    key="ev:" + str(int(st)),               # una vez por evento
                )
