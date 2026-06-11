"""Tool registry — builds FunctionSchemas from config/tools.yaml and registers
handlers on the LLM service (PLAN_FINAL §3.1, §9.1).

- read_only tools execute directly.
- side_effect tools NEVER execute on first call: they go through the verbal
  confirmation flow in security.py (plus taint mode forces confirmation for
  everything after web content in the same turn).
- Every registration sets timeout_secs (pipecat 1.x default is None = hang).
"""

import functools
from pathlib import Path

import yaml
from loguru import logger

from pipecat.adapters.schemas.function_schema import FunctionSchema

from . import camera, n8n, web

TOOLS_YAML = Path("/config/tools.yaml")

BUILTINS = {
    "web_search": web.web_search,
    "web_read": web.web_read,
    "ver_camara": camera.ver_camara,
}


def _schema_from_yaml(name: str, spec: dict) -> FunctionSchema:
    props, required = {}, []
    for pname, p in (spec.get("parameters") or {}).items():
        props[pname] = {"type": p.get("type", "string"), "description": p.get("description", "")}
        if p.get("required"):
            required.append(pname)
    return FunctionSchema(
        name=name,
        description=spec["description"].strip(),
        properties=props,
        required=required,
    )


def register_tools(llm, security) -> list[FunctionSchema]:
    config = yaml.safe_load(TOOLS_YAML.read_text(encoding="utf-8"))
    schemas: list[FunctionSchema] = []

    for name, spec in (config.get("tools") or {}).items():
        if not spec.get("enabled", False):
            logger.info(f"tool {name}: disabled")
            continue

        timeout = spec.get("timeout_secs", 15)

        if "builtin" in spec:
            impl = functools.partial(BUILTINS[spec["builtin"]], security=security)
        elif "n8n_webhook" in spec:
            impl = functools.partial(n8n.call_webhook, path=spec["n8n_webhook"])
        else:
            logger.warning(f"tool {name}: no builtin/n8n_webhook, skipped")
            continue

        side_effect = spec.get("type") == "side_effect"

        async def handler(params, _impl=impl, _name=name, _side=side_effect):
            args = dict(params.arguments or {})
            try:
                if _side or security.tainted:
                    # §9.1.1 + §9.1.6: defer to verbal confirmation outside the LLM.
                    result = security.request_confirmation(
                        _name, args, lambda a, _i=_impl: _i(**a)
                    )
                else:
                    result = await _impl(**args)
            except Exception as e:
                logger.exception(f"tool {_name} failed")
                result = {"status": "error", "mensaje": str(e)}
            await params.result_callback(result)

        # TODO(Fase 1): confirm register_function kwargs on 1.3.0
        # (cancel_on_interruption=True is the default; timeout_secs per function).
        llm.register_function(name, handler, timeout_secs=timeout)
        schemas.append(_schema_from_yaml(name, spec))
        logger.info(f"tool {name}: registered ({spec.get('type')}, timeout={timeout}s)")

    # Confirmation tool — the ONLY path that executes a pending side-effect,
    # and it re-checks the user's real utterance in plain code (security.py).
    async def confirmar_accion(params):
        await params.result_callback(await security.try_execute_pending())

    llm.register_function("confirmar_accion", confirmar_accion, timeout_secs=20)
    schemas.append(
        FunctionSchema(
            name="confirmar_accion",
            description=(
                "Ejecuta la acción pendiente DESPUÉS de que el usuario haya "
                "confirmado de viva voz. Llámala solo tras oír su confirmación."
            ),
            properties={},
            required=[],
        )
    )
    return schemas
