"""Tests de la capa de tools reutilizable (registry): specs + dispatch + seguridad."""

import asyncio

from security_core import SecurityState
from tools.registry import dispatch, tool_specs


def test_specs_include_key_tools():
    names = {s["function"]["name"] for s in tool_specs()}
    for t in ("encargar", "programar_tarea", "listar_tareas", "cancelar_tarea",
              "consultar_agenda", "recordar", "investigar", "confirmar_accion"):
        assert t in names, f"falta la tool {t} en el registro de texto"


def test_encargar_requires_confirmation():
    # side_effect: NO se ejecuta; queda pendiente de confirmación (defensa central).
    sec = SecurityState()
    r = asyncio.run(dispatch("encargar", {"tarea": "reiniciar el panel"}, sec))
    assert r.get("status") == "pending_confirmation" and sec.pending is not None


def test_unknown_tool_is_handled():
    r = asyncio.run(dispatch("herramienta_inexistente", {}, SecurityState()))
    assert r.get("status") == "error"


def test_confirmar_without_pending_is_safe():
    r = asyncio.run(dispatch("confirmar_accion", {}, SecurityState()))
    assert r.get("status") == "error"   # no hay nada que confirmar -> no ejecuta nada


def test_invented_args_are_filtered():
    # consultar_agenda no tiene parámetros; un arg inventado no debe reventar.
    r = asyncio.run(dispatch("consultar_agenda", {"pendiente": False}, SecurityState()))
    assert isinstance(r, dict)   # devuelve algo, no excepción
