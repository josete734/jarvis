---
tipo: bitácora
sesión: S7
fecha: 2026-06-17
proyecto: "[[J.A.R.V.I.S. MOC]]"
tags: [jarvis, bitácora, sprint]
---

# Bitácora S7 — Cierre de sprint (2026-06-17)

> Sprint de expansión y consolidación: de "voz que funciona" a "mayordomo capaz, proactivo y con red de seguridad". Cerrado con tests, documentación y versión final.

## Qué se construyó

### 📱 Telegram bidireccional
Jarvis pasa de solo *empujar* avisos a **conversar por texto** con el mismo cerebro (GLM-5), herramientas y memoria que por voz. Solo responde al dueño. Lo hablado por texto también alimenta la memoria. Ver [[Anexo - Canales]] (pendiente).

### 👁️ Routing por presencia (Fase B de la cámara)
El sistema decide el canal según dónde estás: **presente → voz**, **ausente → Telegram**, **noche/DND → Telegram silencioso**. Con *fail-safe*: sin cámara, asume presente (como antes). Regla añadida: **un mensaje de Telegram = estás fuera** → no te habla a una casa vacía.

### ⏰ Cron en lenguaje natural + monitores
Tareas recurrentes ("cada mañana dame el tiempo") y **monitores** que solo avisan si hay algo (patrón `[SILENT]`). Decisión de seguridad: **no ejecuta scripts arbitrarios**, solo prompts con las herramientas ya sandboxed.

### 🛠️ Delegación de ACCIONES a Claude Code (con guardarraíles)
La tool `encargar` deja a Jarvis *hacer cosas* en el servidor (crear/editar archivos, docker, systemctl). Tres capas de seguridad:
1. **Confirmación determinista** (arreglado el bucle de "¿confirmas?").
2. **Doble confirmación inteligente** — Jarvis juzga el riesgo y, si es destructivo, avisa y pide confirmación rotunda.
3. **Guardia de comandos** (hook PreToolUse) — bloquea `rm -rf /`, `mkfs`, etc., pase lo que pase. Sudo acotado a docker/systemctl/apt.

> Principio clave: *la última defensa nunca debe ser un prompt*. La inteligencia decide; el guardia determinista es el suelo.

### 🧠 Memoria que aprende y olvida
Refactor del almacén: tabla `facts` con **recall** (lo que usas sube de prioridad) y **decay** (lo que no se menciona en 30/90 días se archiva, sin borrar). `aprendido.md` pasa a ser la *vista rankeada*. Ver [[Concepto - Memoria]].

### 🧪 Calidad
- Clasificador de errores del LLM (reintenta, comprime contexto, mensajes específicos).
- **Suite de 68 tests** + verificación en vivo de todo el sistema (servicios, guardia, tools, bridge, sudoers, confirmación).

## Decisiones y descartes
- **Bloque 5 (Prometheus/Grafana)**: descartado — sobre-ingeniería para un homelab personal; el HUD ya da métricas básicas.
- **Tools `todo`/`clarify`**: descartadas — son para agentes de coding autónomos, no para un mayordomo conversacional.
- **Recall scoring de 6 factores completo**: simplificado a recencia+recall+frecuencia (encaja mejor en el stack actual).

## Origen de las ideas
Análisis línea-a-línea de **openclaw** y **hermes-agent** (5 agentes en paralelo). Lo aprovechable se documentó en `docs/PLAN_MEJORAS.md`. ACP descartado (sobre-ingeniería).

## Pendiente
- ⏳ **Fase C (cámara)**: solo falta la webcam física + enrolar la cara. Todo el código listo (`docs/CAMERA_FASE_C.md`).
- 🔁 Rodaje en uso real antes de seguir añadiendo.
- 🔑 Rotar secretos filtrados en chat (OpenCode, Telegram, Spotify) y `git push` a GitHub (commit ya hecho en local).

## Incidencias resueltas
- **Spotify no salía en pantalla**: el HUD machacaba la API (429, penalización ~10 h). Arreglado con caché de 8 s.
- **Anker se desconectó del USB** (caída de voz no causada por código).
- **Bucle de confirmación** en Telegram: el LLM re-llamaba la tool en vez de confirmar → confirmación movida a código.

---
*Anterior: [[Bitácora S6]] · Siguiente: [[Bitácora S8]]*
