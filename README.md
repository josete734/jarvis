# J.A.R.V.I.S. — Asistente de voz local-first (homelab M70q)

Asistente personal de voz en español de España sobre un Lenovo ThinkCentre M70q
(i5-10400T, 16 GB, sin GPU): wake word + STT + TTS + memoria + visión locales,
razonamiento LLM en Groq vía LiteLLM con failover.

> **¿Server recién instalado? Empieza por [`BOOTSTRAP.md`](BOOTSTRAP.md).**
> Te deja con Claude Code dentro del repo y todo el contexto cargado.

**Documento rector**: [`docs/PLAN_FINAL.md`](docs/PLAN_FINAL.md) (v3, 11-jun-2026,
verificado contra fuentes oficiales). Checklist por fases: [`docs/FASES.md`](docs/FASES.md).

## Estado

Esqueleto **verificado contra el código fuente real** de las librerías
(Pipecat v1.3.0, openWakeWord v0.6.0, mem0 v1.0.11, ultralytics, insightface) —
ver [`docs/VERIFICACION_APIS.md`](docs/VERIFICACION_APIS.md). Aún no ejecutado en
hardware: **la primera ejecución en el M70q es la Fase 1**. Los puntos que solo
se validan ejecutando quedan marcados como `TODO` en el código.

## Trabajar con Claude Code

El repo trae tooling de Claude Code listo (`.claude/` + `CLAUDE.md`):

- **`CLAUDE.md`** — contexto autosuficiente del proyecto (se carga solo al abrir
  `claude` en el repo, incluso en un server sin tu config global).
- **Agente `jarvis-builder`** — ingeniero experto en este stack y sus gotchas;
  delega en él la implementación y depuración.
- **Skills**: `deploy-operate`, `add-n8n-action`, `debug-voice-pipeline`,
  `advance-phase`.
- **`.claude/settings.json`** — permisos para operar el proyecto sin fricción.

```bash
cd /opt/jarvis && claude
# > "Lee CLAUDE.md y docs/FASES.md y guíame en la Fase 0."
```

## Quickstart (en el M70q, Ubuntu Server 24.04)

```bash
sudo bash scripts/install_host.sh          # Fase 0: host (zram, docker, ufw, grupos, dirs)
bash scripts/test_aec.sh plughw:1,0        # prueba de AEC (puerta de la Fase 0)
cp .env.example .env && nano .env          # secretos + RENDER_GID
make build && make models                  # imágenes + modelos (Piper, Whisper, wake, YOLO, e5, caras)
make up && make logs s=orchestrator        # arrancar
sudo tailscale serve --bg --https=443 http://127.0.0.1:8080   # panel al tailnet
```

## Estructura

```
CLAUDE.md · BOOTSTRAP.md     contexto de Claude · arranque desde cero
.claude/                     agente experto, skills, settings
config/                      litellm (modelos+failover) · searxng · tools.yaml · audio
services/
  orchestrator/              Pipecat: bot.py, wakeword_gate, stt_factory, tools/, seguridad
  vision/                    presencia (motion→YOLO→cara) + GET /frame   (Fase 5)
  panel/                     FastAPI + HTMX + identidad Tailscale        (Fase 6)
  reflection/                consolidación nocturna de memoria           (Fase 3)
prompts/ persona/            system prompt, ficha de personalidad, perfil evolutivo (git)
scripts/                     install_host · download_models · test_aec · backup · healthcheck
systemd/                     jarvis.service + timers (reflexión 04:00, backup 05:00)
docs/                        PLAN_FINAL · FASES · RUNBOOK · estudio + investigaciones
.github/workflows/           CI: valida sintaxis Python, YAML y el compose
```

## Decisiones clave (resumen del plan)

- **LLM**: Groq Developer tier; A/B/C en Fase 2 (`llama-3.3-70b` favorito) —
  cambiar de modelo = 1 línea en `config/litellm/config.yaml`.
- **STT**: whisper small INT8 en v1 → parakeet v3 en Fase 2-3
  (`STT_BACKEND=openai` + perfil `stt-parakeet`).
- **Seguridad del agente** ([`docs/PLAN_FINAL.md`](docs/PLAN_FINAL.md) §9.1):
  confirmación verbal para acciones, guard SSRF, spotlighting, HMAC en webhooks,
  taint mode. No dar de alta webhooks con efecto real sin esto.
- **Voz**: siempre por micro/altavoz USB del servidor (v1). El acceso remoto es
  solo al panel, por Tailscale.
