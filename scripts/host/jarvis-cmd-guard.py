#!/usr/bin/env python3
"""jarvis-cmd-guard — hook PreToolUse de Claude Code para las acciones de `encargar`.

Enforcement DETERMINISTA en el host (fuera del LLM): inspecciona cada comando Bash
que el operador Claude Code intenta ejecutar y BLOQUEA los catastróficos/irreversibles,
aunque el modelo los proponga. Es una DENY-LIST (deja pasar lo normal, corta lo letal):
no sustituye a la confirmación de Jarvis, la respalda.

Protocolo de hook: lee JSON por stdin ({tool_name, tool_input:{command}}). Si el
comando casa una regla letal -> exit 2 + motivo por stderr (Claude lo trata como
denegado). Si no -> exit 0 (permitido). Ante error de parseo -> exit 0 (no rompe
tareas legítimas; el guardia es una capa extra, no la única).

Registra cada decisión en /srv/jarvis/logs/cmd_guard.log.
"""

import json
import re
import sys
import time
from pathlib import Path

LOG = Path("/srv/jarvis/logs/cmd_guard.log")

# Patrones LETALES (irreversibles / cargarse el sistema o el home). Case-insensitive.
LETHAL = [
    r"\brm\s+(-[a-z]*\s+)*-?[rf]{1,2}\b[^|;&]*\s(/|/\*|~|\$HOME|/home|/etc|/var|/usr|/boot|/srv|/opt|/bin|/lib)(\s|/|$)",
    r"\bmkfs\b", r"\bmke2fs\b", r"\bwipefs\b", r"\bshred\b",
    r"\bdd\b[^|;&]*\bof=/dev/(sd|nvme|vd|mmcblk|disk)",
    r">\s*/dev/(sd|nvme|vd|mmcblk)",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;",                 # fork bomb
    r"\bchmod\s+(-[a-z]*\s+)*-R\s+[0-7]{3,4}\s+(/|/etc|/usr|/var|/home|/srv|/opt)(\s|$)",
    r"\bchown\s+(-[a-z]*\s+)*-R\s+[^|;&]*\s(/|/etc|/usr|/var|/srv|/opt)(\s|$)",
    r"\b(fdisk|parted|sgdisk|gdisk)\b[^|;&]*/dev/",
    r">\s*/etc/(passwd|shadow|sudoers|fstab)\b",
    r"\bgit\b[^|;&]*\breset\s+--hard\b[^|;&]*\bHEAD~",       # destructivo de histórico (heurístico suave)
    r"\buserdel\b", r"\bdeluser\b",
    r"\biptables\s+-F\b", r"\bufw\s+(--force\s+)?reset\b",   # tirar el firewall
    r"\bsystemctl\s+(stop|disable|mask)\s+(ssh|sshd|tailscaled|cloudflared)\b",  # cortarse el acceso
    r"\btruncate\s+-s\s*0\s+[^|;&]*/(etc|srv|opt|var)\b",
    r"\bJARVIS_GUARD_SELFTEST\b",                            # centinela para probar el wiring sin riesgo
]
_RE = [re.compile(p, re.IGNORECASE) for p in LETHAL]

# Ficheros con SECRETOS: ni investigar ni encargar tienen por qué leerlos/tocarlos.
# Fail-closed para cualquier herramienta (Read/Edit/Glob/Grep/Write/Bash) que los
# referencie -> cierra la exfiltración de credenciales vía una tarea delegada
# (o un prompt-injection). .env.example (plantilla sin secretos) sí se permite.
SECRET_RE = re.compile(
    r"\.env(?!\.example)\b|\.env$|/\.ssh/|\bid_ed25519\b|\bid_rsa\b|\.restic-pass"
    r"|spotify_refresh|/root/|/etc/(shadow|sudoers)|\.npy\b",
    re.IGNORECASE,
)


def _log(decision: str, cmd: str, rule: str = "") -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {decision}\t{rule}\t{cmd[:300]}\n")
    except Exception:
        pass


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0                                            # no parseable -> no bloquear (capa extra)
    tool = data.get("tool_name") or ""
    ti = data.get("tool_input") or {}

    # 1) Guardia de SECRETOS (todas las herramientas): bloquea acceso a .env, claves,
    #    restic-pass, /root, biometría .npy... en file_path/pattern/glob/command/edits.
    blob = " ".join(str(ti.get(k, "")) for k in
                    ("file_path", "path", "pattern", "glob", "command", "old_string", "new_string"))
    if SECRET_RE.search(blob):
        _log("BLOCK-SECRET", blob, "secret-path")
        sys.stderr.write(
            "BLOQUEADO por jarvis-cmd-guard: las tareas delegadas no pueden leer ni tocar "
            "ficheros con secretos (.env, claves SSH, restic-pass, etc.). Si hace falta, que lo haga el usuario.\n")
        return 2

    # 2) Deny-list de comandos letales (solo Bash).
    if tool not in ("Bash", "bash"):
        return 0
    cmd = (ti.get("command") or "")
    if not cmd:
        return 0
    for rx in _RE:
        if rx.search(cmd):
            _log("BLOCK", cmd, rx.pattern)
            sys.stderr.write(
                "BLOQUEADO por jarvis-cmd-guard: comando potencialmente destructivo/irreversible. "
                "No ejecutes esto. Si el usuario lo necesita de verdad, que lo haga él manualmente.\n")
            return 2                                        # exit 2 = denegar en Claude Code
    _log("ALLOW", cmd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
