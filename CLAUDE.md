# CLAUDE.md — Proyecto J.A.R.V.I.S.

Asistente de voz local-first para homelab sobre un Lenovo ThinkCentre M70q.
Este archivo es tu contexto al abrir el proyecto. **Antes de tocar nada, lee
`docs/PLAN_FINAL.md` (documento rector) y `docs/FASES.md` (en qué fase estamos).**

## Quién es José y cómo trabajar con él
- **Responde siempre en español.** Código, commits, nombres de variables y
  identificadores en inglés.
- Commits con formato `type(scope): description` (p. ej. `feat(orchestrator): add wake gate`).
- **Confirma antes de añadir, quitar o actualizar dependencias.**
- Si un cambio requiere más de 3 archivos nuevos, **propón el plan primero**.
- Pregunta antes de reestructurar directorios o mover archivos entre módulos.
- Si algo es ambiguo, presenta 2-3 opciones concretas antes de actuar.
- Package manager del lado web (si lo hubiera): pnpm, nunca npm/yarn. En este
  repo el grueso es Python + Docker.

## Qué es este proyecto (resumen; el detalle está en docs/PLAN_FINAL.md)
- **Hardware**: M70q i5-10400T, 16 GB RAM, sin GPU dedicada, iGPU Intel UHD 630.
  NVMe M.2 (SO+Docker+modelos) + SSD SATA 1 TB (datos) + USB (backups). Ubuntu 24.04.
- **Pipeline de voz**: openWakeWord ("hey jarvis", gate custom) → Silero VAD +
  smart-turn → STT (faster-whisper small → parakeet) → LLM (Groq vía LiteLLM) →
  Piper TTS (es_ES-davefx). Todo orquestado con **Pipecat 1.3.0**.
- **Cerebro**: Groq Developer tier; A/B/C en Fase 2 (favorito `llama-3.3-70b-versatile`);
  failover LiteLLM → Cerebras `gpt-oss-120b` → Gemini Flash.
- **Memoria**: mem0 OSS 1.x + Chroma + embeddings e5-small. Reflexión nocturna.
- **Acciones**: n8n (webhooks firmados con HMAC). **Búsqueda**: SearXNG propio.
- **Visión**: presencia escalonada (movimiento→YOLO11n OpenVINO→InsightFace) + cámara bajo demanda.
- **Panel**: FastAPI + HTMX, accesible solo por Tailscale (identidad del tailnet).

## Reglas de trabajo específicas del proyecto
1. **El documento rector es `docs/PLAN_FINAL.md` (v3, verificado 11-jun-2026).**
   Ante conflicto con `docs/estudio_consolidado.md` o las investigaciones, manda
   el plan. El estudio y las investigaciones son contexto de fondo.
2. **Trabaja fase a fase** siguiendo `docs/FASES.md`. No te adelantes; cada fase
   tiene criterios de éxito verificables. Marca el progreso ahí.
3. **El esqueleto se verificó contra el código fuente real** de las librerías
   (Pipecat v1.3.0, openWakeWord v0.6.0, mem0 v1.0.11, ultralytics, insightface)
   — ver `docs/VERIFICACION_APIS.md`. Aún NO se ha ejecutado en hardware: la
   primera ejecución en el M70q es la Fase 1, y quedan `TODO` genuinos (los que
   solo se validan ejecutando). Si una API real difiere, **verifica en la
   doc/fuente oficial antes de cambiar — no inventes firmas ni nombres de módulos**.
   Una oleada de revisión adversarial (11-jun-2026) corrigió 15 hallazgos de arranque,
   seguridad y operaciones — registro en `docs/VERIFICACION_APIS.md`.
4. Al inicio de cada fase, **revisa las deprecations de Groq**
   (`console.groq.com/docs/deprecations`) y las notas de versión de Pipecat:
   el catálogo de modelos y la API rotan rápido.
5. **Verificación honesta**: no marques algo como hecho sin probarlo. Si un test
   falla, dilo con el output. Si saltas un paso, dilo.
6. **Seguridad innegociable** (docs/PLAN_FINAL.md §9.1): no des de alta ninguna
   tool `side_effect` (webhooks n8n con efecto real) sin la confirmación verbal
   fuera del LLM, el guard SSRF de web_read, el spotlighting y el HMAC. El
   asistente cumple la "lethal trifecta" — trátalo con ese cuidado.
7. Para acciones destructivas o de sistema (borrar datos, `sudo`, reiniciar
   servicios) **confirma antes**. Reportes de estado con datos reales.

## Herramientas de este repo
- **Agente experto**: usa el subagente `jarvis-builder` para implementar o
  depurar cualquier parte del stack — conoce todas las decisiones y gotchas.
- **Skills** (invócalas cuando apliquen):
  - `deploy-operate` — arrancar/parar/logs/healthcheck/systemd/tailscale serve.
  - `add-n8n-action` — añadir una acción n8n nueva (webhook HMAC + confirmación).
  - `debug-voice-pipeline` — diagnosticar audio, wake word, STT, latencia, barge-in.
  - `advance-phase` — checklist y validación para pasar de fase.
- **Operación**: `docs/RUNBOOK.md`, el `Makefile`, y `BOOTSTRAP.md` (arranque desde cero).

## Dónde estamos
Server virgen → **Fase 0** (preparar el host + prueba de AEC). Sigue `BOOTSTRAP.md`.
