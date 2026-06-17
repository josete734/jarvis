"""Capa de tools reutilizable FUERA de Pipecat (canal de texto, Fase A).

`tools/__init__.py` registra las tools en el `OpenAILLMService` de Pipecat (voz).
Este módulo expone la MISMA lógica (mismos BUILTINS, mismo `tools.yaml`, misma
semántica de seguridad: filtro de args + confirmación de side_effect + taint)
pero en una forma plana usable por un bucle de chat-completions propio:

- `tool_specs()` -> lista de tools en formato OpenAI tool-calling.
- `dispatch(name, args, security)` -> ejecuta y devuelve el resultado (dict).

Una sola fuente de verdad de tools/seguridad; el canal de texto NO duplica reglas.
"""

from pathlib import Path

import yaml
from loguru import logger

from . import agenda, briefing, camera, cron_tools, encargar, memoria, n8n, reminders, research, web

TOOLS_YAML = Path("/config/tools.yaml")

BUILTINS = {
    "web_search": web.web_search,
    "web_read": web.web_read,
    "ver_camara": camera.ver_camara,
    "consultar_agenda": agenda.consultar_agenda,
    "investigar": research.investigar,
    "encargar": encargar.encargar,
    "crear_recordatorio": reminders.crear_recordatorio,
    "recordar": memoria.recordar,
    "briefing_matutino": briefing.briefing_matutino,
    "programar_tarea": cron_tools.programar_tarea,
    "listar_tareas": cron_tools.listar_tareas,
    "cancelar_tarea": cron_tools.cancelar_tarea,
}

_SPECS: list | None = None
_META: dict | None = None


def _load() -> tuple[list, dict]:
    config = yaml.safe_load(TOOLS_YAML.read_text(encoding="utf-8"))
    specs: list = []
    meta: dict = {}
    for name, spec in (config.get("tools") or {}).items():
        if not spec.get("enabled", False):
            continue
        if "builtin" in spec:
            impl = BUILTINS.get(spec["builtin"])
            if impl is None:
                continue
            kind = "builtin"
        elif "n8n_webhook" in spec:
            impl = n8n.call_webhook
            kind = "n8n"
        else:
            continue
        params = spec.get("parameters") or {}
        props, required = {}, []
        for pn, p in params.items():
            props[pn] = {"type": p.get("type", "string"), "description": p.get("description", "")}
            if p.get("required"):
                required.append(pn)
        meta[name] = {
            "impl": impl,
            "kind": kind,
            "path": spec.get("n8n_webhook"),
            "side": spec.get("type") == "side_effect",
            "known": set(params.keys()),
        }
        specs.append({"type": "function", "function": {
            "name": name,
            "description": spec["description"].strip(),
            "parameters": {"type": "object", "properties": props, "required": required},
        }})
    # confirmar_accion: la ÚNICA vía que ejecuta una acción pendiente (igual que en voz).
    specs.append({"type": "function", "function": {
        "name": "confirmar_accion",
        "description": ("Ejecuta la acción pendiente DESPUÉS de que el usuario la haya confirmado "
                        "por escrito. Llámala solo tras su confirmación explícita ('sí', 'hazlo')."),
        "parameters": {"type": "object", "properties": {}, "required": []},
    }})
    return specs, meta


def _ensure() -> tuple[list, dict]:
    global _SPECS, _META
    if _SPECS is None:
        _SPECS, _META = _load()
    return _SPECS, _META


def tool_specs() -> list:
    return _ensure()[0]


async def dispatch(name: str, args: dict, security) -> dict:
    """Ejecuta una tool con la misma semántica de seguridad que la voz."""
    _, meta = _ensure()
    if name == "confirmar_accion":
        return await security.try_execute_pending()
    m = meta.get(name)
    if m is None:
        return {"status": "error", "mensaje": f"Herramienta desconocida: {name}."}
    raw = dict(args or {})
    a = {k: v for k, v in raw.items() if k in m["known"]}   # ignora args inventados
    if raw.keys() - m["known"]:
        logger.warning(f"tool {name} (texto): ignoro args inventados {sorted(raw.keys() - m['known'])}")

    def _run(aa: dict):
        if m["kind"] == "builtin":
            return m["impl"](security=security, **aa)
        return m["impl"](path=m["path"], **aa)

    try:
        if m["side"] or security.tainted:
            # side_effect/taint: NO se ejecuta; queda pendiente de confirmación explícita.
            return security.request_confirmation(name, a, lambda aa: _run(aa))
        return await _run(a)
    except Exception:
        logger.exception(f"tool {name} failed (texto)")
        return {"status": "error", "mensaje": "No he podido completar esa consulta ahora mismo."}
