---
name: advance-phase
description: >-
  Úsala para pasar de una fase del proyecto a la siguiente: validar los criterios
  de la fase actual, activar lo que toca y marcar el checklist. Cuando José diga
  "siguiente fase", "ya funciona X, sigamos", "qué falta para la fase N".
---

# Avanzar de fase

El plan de fases está en `docs/FASES.md` (criterios) y `docs/PLAN_FINAL.md §11`
(detalle). Trabaja una fase a la vez.

## Procedimiento
1. **Verifica los criterios de la fase actual** en `docs/FASES.md`. No marques una
   casilla sin haberla probado de verdad (reporta el resultado real).
2. **Revisa deprecations y versiones** antes de empezar la nueva fase:
   - Groq: `console.groq.com/docs/deprecations` (el catálogo rota; Maverick, Kimi
     ya retirados en 2026).
   - Pipecat: notas de versión (breaking changes entre 1.x).
3. **Activa lo que la fase enciende** (variables de entorno del compose):
   - Fase 2-3 (STT parakeet): `STT_BACKEND=openai` + `make parakeet-on`.
   - Fase 3 (memoria): `MEM0_ENABLED=true` → reinicia orchestrator → comprueba el
     self-test del prefijo e5 en logs.
   - Fase 4 (acciones): habilita las tools en `config/tools.yaml` tras montar las
     medidas de seguridad §9.1 (skill `add-n8n-action`).
   - Fase 5 (visión): `DISABLE_PRESENCE=false`; revalida el modelo de visión de Groq.
4. **Marca el checklist** en `docs/FASES.md` y haz commit: `git commit -m "feat(faseN): ..."`.

## Mapa de fases (resumen)
- **0** Base: host + Tailscale + Docker + **prueba de AEC** (puerta).
- **1** Oídos y voz: wake gate + VAD/smart-turn + whisper + Piper (eco hablado).
- **2** Cerebro: LiteLLM + Developer tier + personalidad + **A/B/C de modelo**.
- **2-3** STT: cambio a parakeet (config, sin código).
- **3** Memoria: mem0 + e5 con prefijos + reflexión + origin/no-extract en turnos web.
- **4** Acciones e internet: n8n + HMAC + SearXNG + **seguridad v1 completa**.
- **5** Presencia y visión: vision (driver Gen9) + YOLO11n + InsightFace + ver_camara.
- **6** Panel: FastAPI + tailscale serve (identidad) + métricas de latencia.
- **7** Refinamiento: speaker-ID, parakeet propio, Supertonic, mem0 2.x, voz móvil, etc.

## Recordatorio
Si una API real difiere del esqueleto (marcadores `TODO(Fase N)`), verifica en la
doc oficial antes de cambiar. No inventes firmas. Delega la implementación fina al
agente `jarvis-builder`.
