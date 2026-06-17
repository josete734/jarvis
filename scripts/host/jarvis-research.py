#!/usr/bin/env python3
"""jarvis-research — puente para que Jarvis (Mycroth) delegue investigaciones a
Claude Code. Corre en el HOST como jose (usa la auth y los TOKENS de Claude del
usuario, no los de OpenCode). Asíncrono: arranca `claude -p` y, al terminar, hace
que Jarvis lo diga por voz (callback a /event/say del orquestador).

SEGURIDAD:
- /research exige el secreto compartido (EVENTS_SECRET), igual que el orquestador.
- claude se ejecuta con SOLO herramientas de lectura/web (WebSearch, WebFetch,
  Read, Grep, Glob). NUNCA Bash/Write/Edit -> una orden de voz jamás puede
  ejecutar comandos ni modificar ficheros del sistema.
"""

import json
import os
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

CLAUDE = os.getenv("CLAUDE_BIN", "/home/jose/.local/bin/claude")
ALLOWED = ["WebSearch", "WebFetch", "Read", "Grep", "Glob"]   # /research: solo lectura/web
# /do (acciones): amplio en el homelab COMO jose, SIN sudo/root. La confirmación
# se exige a nivel de Jarvis (tool side_effect), no aquí.
ACTIONS_ALLOWED = ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch"]
ACTIONS_ON = os.getenv("JARVIS_ACTIONS", "on").lower() != "off"   # kill-switch
ACTIONS_CWD = os.getenv("ACTIONS_CWD", "/home/jose")             # raíz de trabajo (como jose)
GUARD_SETTINGS = os.getenv("GUARD_SETTINGS", "/home/jose/jarvis-claude-settings.json")  # hook deny letal
MODEL = os.getenv("RESEARCH_MODEL", "")                        # vacío = modelo por defecto de claude
ORCH = os.getenv("ORCH_EVENTS", "http://127.0.0.1:8070")
PORT = int(os.getenv("RESEARCH_PORT", "8077"))
OUTDIR = Path("/srv/jarvis/logs/research")
ACTDIR = Path("/srv/jarvis/logs/actions")
TIMEOUT = int(os.getenv("RESEARCH_TIMEOUT", "600"))
ACTIONS_TIMEOUT = int(os.getenv("ACTIONS_TIMEOUT", "900"))
SECRET = ""


def _load_secret() -> None:
    global SECRET
    SECRET = os.getenv("EVENTS_SECRET", "")
    if not SECRET:
        try:
            for line in Path("/opt/jarvis/.env").read_text(encoding="utf-8").splitlines():
                if line.startswith("EVENTS_SECRET="):
                    SECRET = line.split("=", 1)[1].strip()
                    break
        except Exception:
            pass


def _say(text: str) -> None:
    # El aviso de cierre (éxito o fallo) es la única señal que recibe el usuario de
    # que una tarea terminó; se reintenta para no perderlo por un fallo de red puntual.
    for intento in range(3):
        try:
            req = urllib.request.Request(
                ORCH + "/event/say",
                data=json.dumps({"text": text}).encode(),
                headers={"Content-Type": "application/json", "X-Jarvis-Events-Secret": SECRET},
            )
            urllib.request.urlopen(req, timeout=12)
            return
        except Exception as e:
            print(f"[research] aviso por voz falló (intento {intento + 1}/3): {e}", flush=True)
            time.sleep(3)


def _run(rid: str, tema: str) -> None:
    prompt = (
        f"Eres el equipo de investigación de un mayordomo de voz español. "
        f"Investiga a fondo, con búsqueda web si hace falta: «{tema}». "
        f"Devuelve un resumen en ESPAÑOL de 3 a 5 frases, claro y al grano, "
        f"SIN markdown, listas ni símbolos (se va a leer en voz alta). "
        f"Si no encuentras nada fiable, dilo en una frase."
    )
    cmd = [CLAUDE, "-p", prompt, "--output-format", "text", "--allowedTools", *ALLOWED]
    if MODEL:
        cmd += ["--model", MODEL]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        out = (r.stdout or "").strip()
        if not out:
            out = "No he obtenido un resultado claro de la investigación, señor."
    except subprocess.TimeoutExpired:
        out = "La investigación se ha alargado demasiado y la he detenido, señor."
    except Exception as e:
        print(f"[research {rid}] error: {e}", flush=True)
        out = "No he podido completar la investigación, señor."
    try:
        OUTDIR.mkdir(parents=True, exist_ok=True)
        (OUTDIR / f"{rid}.md").write_text(f"# {tema}\n\n{out}\n", encoding="utf-8")
    except Exception:
        pass
    speak = out if len(out) <= 700 else out[:680] + "…"
    _say(f"Señor, ya tengo lo que me pidió sobre {tema}. {speak}")
    print(f"[research {rid}] hecho en {int(time.time() - t0)}s ({len(out)} ch)", flush=True)


def _run_action(rid: str, tarea: str) -> None:
    """Ejecuta una TAREA REAL con Claude Code (Bash/Write/Edit) como jose, sin sudo."""
    prompt = (
        f"Eres el operador del homelab de José (un mayordomo de voz). Actúas en su "
        f"servidor COMO el usuario jose, en {ACTIONS_CWD}. TAREA: «{tarea}».\n"
        f"Puedes usar `sudo` SOLO para gestionar el homelab: docker / docker compose "
        f"(contenedores), systemctl (servicios) y apt (paquetes). NO intentes otros usos "
        f"de sudo ni root arbitrario (no están permitidos y fallarán). Para docker no hace "
        f"falta sudo (jose está en el grupo docker). El stack vive en /opt/jarvis "
        f"(`cd /opt/jarvis && docker compose ...`). NO ejecutes comandos "
        f"destructivos (borrados masivos, formatear, tocar el sistema) salvo que la "
        f"tarea lo pida explícitamente y sin ambigüedad. Si la tarea es peligrosa o "
        f"poco clara, NO la hagas y explica por qué. Haz el trabajo de forma concreta "
        f"y comprueba el resultado. Al terminar, RESUME en ESPAÑOL en 2-4 frases qué "
        f"has hecho (o por qué no), SIN markdown ni símbolos (se leerá en voz alta)."
    )
    cmd = [CLAUDE, "-p", prompt, "--output-format", "text", "--allowedTools", *ACTIONS_ALLOWED]
    if GUARD_SETTINGS:                          # hook PreToolUse que bloquea comandos letales
        cmd += ["--settings", GUARD_SETTINGS]
    if MODEL:
        cmd += ["--model", MODEL]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=ACTIONS_TIMEOUT, cwd=ACTIONS_CWD)
        out = (r.stdout or "").strip() or "He terminado, señor, aunque no tengo un resumen claro de lo hecho."
    except subprocess.TimeoutExpired:
        out = "La tarea se ha alargado demasiado y la he detenido, señor."
    except Exception as e:
        print(f"[action {rid}] error: {e}", flush=True)
        out = "No he podido completar la tarea, señor."
    try:
        ACTDIR.mkdir(parents=True, exist_ok=True)
        (ACTDIR / f"{rid}.md").write_text(f"# {tarea}\n\n{out}\n", encoding="utf-8")
    except Exception:
        pass
    speak = out if len(out) <= 700 else out[:680] + "…"
    _say(speak)
    print(f"[action {rid}] hecho en {int(time.time() - t0)}s ({len(out)} ch)", flush=True)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path not in ("/research", "/do", "/power"):
            return self._send(404, {"error": "not found"})
        if not SECRET or self.headers.get("X-Jarvis-Events-Secret", "") != SECRET:
            return self._send(401, {"error": "unauthorized"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            body = {}
        if self.path == "/power":
            # Reposo de recursos ("Descansa"/"Revive"): apaga/enciende la pantalla del
            # kiosko. Determinista y SÍNCRONO (no invoca Claude); acotado a sleep|wake.
            action = (body.get("action") or "").strip()
            if action not in ("sleep", "wake"):
                return self._send(400, {"error": "action inválida (sleep|wake)"})
            try:
                r = subprocess.run(
                    ["sudo", "-n", "/usr/local/bin/jarvis-power.sh", action],
                    capture_output=True, text=True, timeout=30,
                )
            except Exception as e:
                return self._send(500, {"error": str(e)[:200]})
            if r.returncode != 0:
                return self._send(500, {"error": (r.stderr or "fallo").strip()[:200]})
            return self._send(200, {"ok": True, "out": (r.stdout or "").strip()[:200]})
        if self.path == "/do":
            if not ACTIONS_ON:
                return self._send(403, {"error": "actions disabled"})
            tarea = (body.get("tarea") or "").strip()
            if not tarea:
                return self._send(400, {"error": "falta tarea"})
            rid = str(body.get("id") or int(time.time()))
            threading.Thread(target=_run_action, args=(rid, tarea[:600]), daemon=True).start()
            return self._send(202, {"status": "en marcha", "id": rid})
        tema = (body.get("tema") or "").strip()
        if not tema:
            return self._send(400, {"error": "falta tema"})
        rid = str(body.get("id") or int(time.time()))
        threading.Thread(target=_run, args=(rid, tema[:400]), daemon=True).start()
        self._send(202, {"status": "en marcha", "id": rid})

    def do_GET(self) -> None:
        if self.path == "/health":
            return self._send(200, {"ok": True})
        return self._send(404, {"error": "not found"})

    def log_message(self, *a) -> None:
        pass


if __name__ == "__main__":
    _load_secret()
    print(f"[bridge] :{PORT} | research tools={ALLOWED} | acciones={'ON' if ACTIONS_ON else 'OFF'} "
          f"tools={ACTIONS_ALLOWED} cwd={ACTIONS_CWD}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
