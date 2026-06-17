# 🎩 J.A.R.V.I.S. — un mayordomo de voz que vive en tu casa

[![CI](https://github.com/josete734/jarvis/actions/workflows/ci.yml/badge.svg)](https://github.com/josete734/jarvis/actions/workflows/ci.yml)

Un asistente de voz personal, en **español de España**, que funciona **entero en un mini-PC tuyo** —
sin enviar tu voz a Amazon, Google ni nadie. Le hablas, te entiende, piensa y te responde como un
mayordomo discreto. Y además hace cosas: te avisa, busca, recuerda y hasta gestiona el servidor.

> Piensa en un Alexa/Google Home… pero **privado, tuyo, y mucho más capaz** — y que se llama Jarvis.

---

## 🧠 ¿Qué es esto, en cristiano?

Es un programa que convierte un ordenador pequeño (un Lenovo de segunda mano) en un **asistente de voz**.
Todo lo importante ocurre **dentro de tu casa**:

- **Te escucha** por un micrófono y se despierta al oír *"hey Mycroft"*.
- **Entiende** lo que dices (lo pasa de voz a texto, en local).
- **Piensa** la respuesta con una inteligencia artificial.
- **Te contesta hablando**, con voz natural.

Lo único que sale a internet es la "parte de pensar" (el modelo de IA) y las búsquedas — tu voz y tus
datos personales **se quedan en casa**.

---

## ✨ ¿Qué sabe hacer?

| Le dices… | …y hace |
|-----------|---------|
| 🗣️ *"Hey Mycroft, ¿qué tiempo hace mañana en Reus?"* | Lo busca y te lo dice |
| 📅 *"¿Qué tengo en la agenda hoy?"* | Mira tu calendario y te lo cuenta |
| ⏰ *"Recuérdame llamar al fontanero a las seis"* | Te avisa a esa hora, por voz |
| 🔁 *"Cada mañana dame el parte del día"* | Tarea recurrente automática |
| 🔔 *"Cada hora avísame si tengo algo urgente"* | **Monitor**: solo te molesta si hay algo |
| 🔎 *"Investiga a fondo qué portátil me compro"* | Delega una investigación seria y te avisa al terminar |
| 🛠️ *"Reinicia el contenedor del panel"* | Ejecuta tareas en el servidor (**con tu confirmación**) |
| 🧠 *"¿Te acuerdas de lo que te conté del coche?"* | Recuerda conversaciones pasadas |
| 📱 *(por Telegram)* *"¿cómo va el servidor?"* | También chateas con él por el móvil cuando no estás en casa |

Y por su cuenta:
- **Aprende solo** de vuestras conversaciones (qué te gusta, tu gente, tus rutinas) — y **olvida** lo que ya no usas.
- **Te pide permiso para apuntar lo que aprende**: te llega una propuesta **por Telegram con botones** (✅ Aprobar · ❌ Rechazar · ✏️ Reformular). Solo si la apruebas se añade a tu perfil — y **cualquier cambio se puede deshacer**.
- **Es proactivo con cabeza**: te avisa de lo importante, pero no es un pesado (por defecto, calla).
- **Sabe si estás en casa**: si estás delante te habla por voz; si escribes por Telegram (estás fuera), te responde por el móvil.
- **Una pantallita** (HUD) muestra qué está haciendo, tu agenda, la música de Spotify y el gasto.

---

## 🔄 ¿Cómo funciona por dentro? (versión simple)

```
   Tú hablas
      │   "hey Mycroft, ¿qué hora es?"
      ▼
 ┌─────────────┐   ┌─────────────┐   ┌──────────────┐   ┌─────────────┐
 │ 1. Te oye   │──▶│ 2. Te       │──▶│ 3. Piensa    │──▶│ 4. Te habla │
 │ (wake word) │   │  entiende   │   │  (IA + tools)│   │  (voz)      │
 │             │   │ (voz→texto) │   │              │   │ (texto→voz) │
 └─────────────┘   └─────────────┘   └──────┬───────┘   └─────────────┘
   micrófono         en tu casa             │             altavoz
                                            ▼
                              ┌───────────────────────────┐
                              │ herramientas: agenda, web, │
                              │ recordatorios, memoria,    │
                              │ acciones en el servidor…   │
                              └───────────────────────────┘
```

*Glosario rápido: **wake word** = la palabra que lo despierta · **STT** = pasar voz a texto ·
**TTS** = pasar texto a voz · **LLM** = el "cerebro" de inteligencia artificial.*

---

## 🖥️ Lo que lleva por dentro (la parte técnica)

- **Hardware**: un Lenovo ThinkCentre M70q (Intel i5-10400T, 16 GB RAM, sin tarjeta gráfica dedicada).
- **Voz (local)**: openWakeWord (*"hey Mycroft"*) · faster-whisper (oír) · Piper (hablar) · todo sobre **Pipecat**.
- **Cerebro**: **GLM-5** a través de OpenCode Go (con LiteLLM y varios modelos de reserva por si uno falla).
- **Tareas difíciles**: delega en **Claude Code** (investigación y acciones en el servidor, con guardarraíles).
- **Memoria**: base de datos local (SQLite) con un sistema que prioriza lo que usas y archiva lo que no.
- **Gobernanza**: lo que aprende pasa por una cola de aprobación; cada cambio del perfil queda en un **registro inmutable** (auditoría) y se puede **deshacer** (rollback).
- **Todo en Docker**: cada pieza en su contenedor, orquestado con `docker compose`.
- **Panel web** (Cloudflare Tunnel + Access) y **bot de Telegram** para controlarlo desde fuera.

> Es un **proyecto personal de homelab** (servidor casero) — hecho para aprender y para uso propio,
> no un producto comercial.

---

## 🚀 Puesta en marcha (si quieres montarlo tú)

Necesitas el mini-PC con Ubuntu Server 24.04 y un micro/altavoz USB (va perfecto un **Anker PowerConf**).

```bash
sudo bash scripts/install_host.sh      # prepara el host (docker, audio, firewall, carpetas)
cp .env.example .env && nano .env      # pon tus claves (IA, Telegram, etc.)
make build && make models              # construye e instala los modelos de voz
make up                                # ¡arranca!
```

Luego, cerca del micro: **"hey Mycroft, ¿qué hora es?"** 🎙️

Guía completa de operación en [`docs/RUNBOOK.md`](docs/RUNBOOK.md). Para añadir la cámara (visión),
[`docs/CAMERA_FASE_C.md`](docs/CAMERA_FASE_C.md).

---

## 📂 El repo por dentro

```
services/
  orchestrator/   el corazón: oye, entiende, piensa, habla, y todas las herramientas
  panel/          la web/pantalla de control (HUD)
  vision/         la cámara: detecta presencia con IA (YOLO + reconocimiento facial)
prompts/ persona/  cómo habla y qué sabe de ti (su "personalidad" y tu perfil)
config/           qué modelo de IA usa, qué herramientas tiene, audio
scripts/          instalación, modelos, backups, diagnóstico
docs/             toda la documentación (ver abajo)
tests/            batería de pruebas automáticas (68, todas en verde ✅)
```

---

## 📚 Documentación

| Documento | Para qué |
|-----------|----------|
| [`docs/FASES.md`](docs/FASES.md) | **Estado actual del proyecto** por fases |
| [`docs/PLAN_FINAL.md`](docs/PLAN_FINAL.md) | El plan maestro original (técnico, a fondo) |
| [`docs/PLAN_MEJORAS.md`](docs/PLAN_MEJORAS.md) | Mejoras robadas de proyectos similares (openclaw, hermes) |
| [`docs/PLAN_PAPERCLIP.md`](docs/PLAN_PAPERCLIP.md) | Gobernanza (auditoría + rollback + cola de aprobación) y backlog priorizado |
| [`docs/CAMERA_FASE_C.md`](docs/CAMERA_FASE_C.md) | Cómo encender la cámara cuando la tengas |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | Operación del día a día |

---

## 🔒 Privacidad y seguridad

- Tu **voz y tus datos** se procesan en casa; solo el razonamiento del modelo y las búsquedas salen a internet.
- Las acciones que tocan el servidor **piden confirmación** y un **guardia** bloquea comandos destructivos.
- Los secretos (claves, tokens) **nunca** se suben al repo (`.gitignore` los protege).

---

*Hecho con cariño (y bastante café) en un homelab. El mayordomo se llama Jarvis; la palabra para
despertarlo es "hey Mycroft" — guiño a Mycroft Holmes, el hermano listo y discreto.*
