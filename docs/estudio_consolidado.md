[TOC]

# 1. Resumen ejecutivo

Este estudio consolida tres fases de investigación y define el plan de implementación completo de **J.A.R.V.I.S.**, un asistente personal de inteligencia artificial para homelab doméstico con conversación de voz en tiempo real, visión, memoria evolutiva, personalidad propia, capacidad de ejecutar acciones (webhooks de n8n), navegación por internet y un centro de control web. El proyecto se despliega sobre un **Lenovo ThinkCentre M70q Tiny** (Intel i5-10400T, 16 GB de RAM, sin GPU dedicada) con **Ubuntu Server 24.04 LTS** y Docker Compose.

Las decisiones clave del estudio son:

1. **Arquitectura híbrida local-first**: todo lo sensible a latencia y privacidad se ejecuta en local (palabra de activación, VAD, transcripción, síntesis de voz, memoria, embeddings, presencia visual, buscador web propio, automatizaciones n8n). Solo el razonamiento del LLM y la visión compleja se delegan a APIs externas ultrarrápidas.
2. **LLM externo en Groq** (`llama-3.3-70b-versatile`, ~276 tok/s, TTFT inferior a 200 ms) con enrutado y failover automático mediante **LiteLLM** hacia Cerebras y Gemini Flash. Coste mensual estimado: entre 0 y 5 € (el free tier de Groq cubre la mayor parte del uso doméstico).
3. **Orquestación con Pipecat** (framework open source BSD-2, 12.700+ estrellas), que integra de forma nativa todos los componentes elegidos: Groq, Cerebras, Piper, Silero VAD, Whisper, mem0 y Moondream, además de *function calling* para las herramientas.
4. **Voz**: Piper `es_ES-davefx-medium` (masculina, español de España, licencia MIT, RTF ≈ 0,2 en CPU, primer audio < 200 ms por frase) como motor principal; Edge-TTS `es-ES-AlvaroNeural` como alternativa de mayor naturalidad cuando hay red.
5. **Memoria y aprendizaje continuo** con mem0 OSS 100 % self-hosted (Chroma + embeddings multilingües en CPU), reflexión nocturna programada y perfil de usuario evolutivo versionado en git.
6. **Presencia proactiva viable**: pipeline escalonado de visión (movimiento → persona → cara) que descarga la inferencia a la iGPU Intel UHD 630 vía OpenVINO, con un consumo en reposo del sistema completo estimado en un 5–10 % de CPU.
7. **Acciones mediante n8n** en el mismo servidor: el LLM invoca *tools* de Pipecat que llaman a webhooks locales de n8n, lo que permite añadir automatizaciones ilimitadas sin tocar el código del asistente.
8. **Navegación por internet nativa** con doble vía: SearXNG self-hosted (metabuscador con API JSON, gratuito e ilimitado) + lector de páginas como herramientas del LLM; y, como atajo, los sistemas `groq/compound` con búsqueda web integrada.
9. **Centro de control web** propio (FastAPI + frontend ligero) accesible solo por Tailscale: estado de servicios, latencias por etapa, transcripciones en vivo, gestión de memorias, edición de la personalidad y activación/desactivación de herramientas. La interacción de voz, sin embargo, es siempre directa por micrófono y altavoz USB conectados al servidor, para latencia mínima.

El sistema completo consume aproximadamente **5–6,5 GB de RAM** de los 16 disponibles y alcanza una **latencia conversacional percibida de ~1,3–2,0 segundos** por turno (con margen de optimización hasta ~1 s), cifras validadas contra los benchmarks y la documentación citada en la sección de referencias.

---

# 2. Objetivos y alcance del proyecto

## 2.1 Visión

Construir un asistente personal estilo J.A.R.V.I.S. (Iron Man) que:

- **Escuche y hable en tiempo real** en español de España, con interrupciones naturales (*barge-in*), mediante un micrófono y un altavoz USB conectados directamente al servidor.
- **Vea**: detecte la presencia del usuario y reaccione (p. ej., saludar al llegar a casa), y pueda describir lo que ve la cámara bajo demanda.
- **Aprenda de cada interacción**: recuerde hechos, preferencias y conversaciones; consolide y corrija sus memorias; y evolucione su relación con el usuario a lo largo de meses y años.
- **Tenga personalidad propia**: ingenioso, leal, con humor seco; consistente entre sesiones y capaz de evolucionar.
- **Actúe**: ejecute acciones reales a través de webhooks de n8n alojados en el mismo servidor (automatizaciones, integraciones, scripts).
- **Navegue por internet de forma nativa**: busque información actual y lea páginas web cuando lo necesite para responder.
- **Sea administrable** desde un centro de control web (logs, latencias, memorias, personalidad, herramientas).

## 2.2 Principios de diseño

| Principio | Implicación práctica |
|---|---|
| **Local-first** | Dependencia externa mínima: solo la inferencia del LLM (y la visión compleja) salen del servidor, siempre como texto/imagen puntual. |
| **Latencia primero** | Streaming en todas las etapas; síntesis por frases; la voz nunca pasa por la nube. |
| **Modularidad** | Cada pieza (STT, LLM, TTS, memoria, herramientas) es intercambiable por configuración, no por reescritura. |
| **Proyecto de años** | Todo versionado en git (prompts, personalidad, configuración), backups automáticos, actualizaciones deliberadas con versiones fijadas. |
| **Privacidad** | Audio y vídeo jamás salen del servidor; al LLM solo viaja texto (y frames puntuales si se pide visión); acceso remoto únicamente por red privada Tailscale. |
| **Legalidad** | Sin clonación de voces de actores reales; voces con licencia abierta entrenadas con datos consentidos. |

## 2.3 Fuera de alcance (por ahora)

Domótica/Home Assistant (la arquitectura la admite en el futuro vía n8n o Wyoming), multiusuario avanzado, y ejecución del LLM principal en local (inviable con calidad conversacional en este hardware, como se justifica en la sección 8).

---

# 3. Análisis del hardware

## 3.1 Plataforma

| Componente | Especificación | Implicación |
|---|---|---|
| CPU | Intel Core i5-10400T, 6 núcleos / 12 hilos, TDP 35 W (Comet Lake) | Suficiente para STT/TTS/VAD locales; insuficiente para LLM 70B o VLM en tiempo real. |
| iGPU | Intel UHD Graphics 630 | Acelerador clave para visión vía OpenVINO (~15 ms por inferencia de detección). |
| RAM | 16 GB DDR4 | Presupuesto total del sistema ~5–6,5 GB → margen amplio. |
| Almacenamiento | NVMe 256 GB + SSD SATA 1 TB | NVMe: SO + Docker + modelos (latencia). SSD: datos persistentes, memoria, backups. |
| Periféricos | Micrófono USB y webcam USB conectados al propio servidor | Audio headless por ALSA; vídeo por V4L2 (`/dev/video0`). |
| Red | Ethernet doméstica (España) | Latencia de ida y vuelta a endpoints de Groq/Cerebras en EE. UU./UE: decenas de ms; irrelevante frente al TTFT. |

## 3.2 Qué puede y qué no puede hacer este equipo

**Puede (verificado en las tres fases de investigación):**

- Transcribir voz en español más rápido que tiempo real con `faster-whisper` (modelos `small`/`medium` cuantizados INT8 en CPU).
- Sintetizar voz natural con Piper a RTF ≈ 0,2 (cinco veces más rápido que tiempo real) con primer audio en menos de 200 ms.
- Mantener palabra de activación + VAD siempre activos con un consumo marginal (1 hilo, < 5 % CPU).
- Ejecutar detección de movimiento continua (~0 % CPU) y detección de personas/caras puntual en la iGPU vía OpenVINO.
- Alojar simultáneamente Chroma, mem0, n8n (+ PostgreSQL), SearXNG (+ Redis), LiteLLM y el panel de control dentro de los 16 GB.

**No puede (y por eso se delega a la nube):**

- Ejecutar un LLM conversacional de calidad: un modelo 7–8B cuantizado Q4 rinde ~3–4 tokens/s en esta CPU (inutilizable en conversación); los modelos 0,5–3B que sí son rápidos carecen de la calidad y el carácter necesarios para un "Jarvis".
- Ejecutar un modelo de visión-lenguaje (VLM) con latencia interactiva: Moondream 2 en CPU tarda segundos por imagen y decenas de segundos en cargar.
- Clonar/entrenar voces localmente (el entrenamiento de una voz Piper requiere GPU; la *inferencia* de la voz resultante sí corre en CPU).

## 3.3 Hardware adicional recomendado

| Elemento | Recomendación | Motivo |
|---|---|---|
| Micrófono | **ReSpeaker USB 4-Mic Array (XVF3000/3800)** o altavoz de conferencia con AEC (Jabra/Anker) | Cancelación de eco acústico por hardware: imprescindible para que Jarvis no se escuche a sí mismo y el *barge-in* funcione de verdad. |
| Altavoz | Cualquier altavoz decente por jack/USB; ideal si es el propio dispositivo de conferencia | Simplifica el AEC. |
| Webcam | USB UVC 1080p estándar | Suficiente para presencia y visión bajo demanda. |
| Coral USB TPU | **NO comprar** | Drivers abandonados por Google (mantenidos solo por la comunidad); la iGPU UHD 630 con OpenVINO cubre el caso de uso gratis. |
| GPU externa | Posponer | Solo se justificaría para LLM/VLM 100 % local en el futuro (≥ 8–12 GB VRAM NVIDIA). |

---

# 4. Arquitectura general del sistema

## 4.1 Diagrama lógico

```
                            ┌──────────────────────── SERVIDOR (M70q, Ubuntu 24.04) ────────────────────────┐
                            │                                                                                │
 [Micrófono USB] ──ALSA──▶  openWakeWord ("hey jarvis") ──▶ Silero VAD ──▶ faster-whisper (es, INT8)        │
                            │                                              │ texto                          │
 [Webcam USB] ──V4L2──▶     Servicio de presencia                          ▼                                │
                            │  (movimiento→persona→cara,    ┌─────────── PIPECAT (orquestador) ──────────┐  │
                            │   OpenVINO en iGPU)           │  Contexto + mem0 (memorias) + personalidad │  │
                            │        │ evento "ha llegado"  │  Function calling:                         │  │
                            │        └──────────────────────▶   • n8n_webhook(...)  ──▶ n8n (local:5678) │  │
                            │                               │   • web_search(...)   ──▶ SearXNG (local)  │  │
                            │                               │   • web_read(url)     ──▶ lector (local)   │  │
                            │                               │   • ver_camara()      ──▶ frame → LLM-V    │  │
                            │                               └───────────────┬────────────────────────────┘  │
                            │                                               │ texto (solo texto sale)       │
                            │                                  LiteLLM ─────┼── failover ──▶ [Cerebras]     │
                            │                                               ▼                [Gemini Flash] │
                            │                                        [GROQ llama-3.3-70b]  (nube, <200ms)   │
                            │                                               │ respuesta en streaming        │
 [Altavoz USB] ◀──ALSA───   Piper TTS (es_ES-davefx) ◀── frases ◀──────────┘                                │
                            │                                                                                │
                            │  mem0+Chroma (memoria) · Reflexión nocturna (cron) · Panel de control (FastAPI)│
                            │  n8n+PostgreSQL · SearXNG+Redis · Tailscale (acceso remoto al panel)           │
                            └────────────────────────────────────────────────────────────────────────────────┘
```

## 4.2 Flujo de un turno de conversación

1. openWakeWord detecta "hey Jarvis" (streaming continuo, ~50–150 ms).
2. Silero VAD delimita el habla; al detectar fin de turno (~200 ms de silencio) cierra el segmento.
3. faster-whisper transcribe en local (0,4–1,2 s para una frase corta).
4. Pipecat inyecta en el contexto: ficha de personalidad + memorias relevantes recuperadas por mem0 + historial reciente.
5. El texto viaja a Groq vía LiteLLM. El LLM responde en *streaming* (primer token en ~0,2–0,6 s) y, si lo necesita, invoca herramientas (n8n, búsqueda web, lectura de páginas, cámara).
6. Pipecat trocea la respuesta por frases y las envía a Piper, que sintetiza la primera frase en < 200 ms mientras el LLM sigue generando.
7. Si el usuario habla encima, el VAD dispara la interrupción: se cancela el TTS y la generación (*barge-in*).
8. mem0 extrae y guarda en segundo plano los hechos nuevos de la conversación.

## 4.3 Auditoría de dependencias externas

| Dependencia | Tipo | Qué sale del servidor | Plan B si falla |
|---|---|---|---|
| Groq API | Crítica (cerebro) | Solo texto (prompt+contexto) | Failover automático a Cerebras → Gemini (LiteLLM); modo offline de emergencia con Qwen 3B local vía Ollama (calidad reducida). |
| Cerebras / Gemini | Respaldo | Solo texto | — |
| Visión cloud (Groq Llama 4 Scout / Gemini) | Opcional | 1 frame JPEG al pedirlo | Responder "no tengo visión avanzada ahora mismo"; Moondream local solo para tareas no interactivas. |
| Edge-TTS | Opcional (voz alternativa) | Texto a sintetizar | Piper local (la opción principal ya es local). |
| Internet (SearXNG consulta motores externos) | Funcional | Términos de búsqueda | El asistente funciona sin internet salvo LLM/búsquedas. |

Todo lo demás —audio, vídeo, transcripción, síntesis, memorias, embeddings, automatizaciones, panel— es 100 % local.

---

# 5. Estado del arte: proyectos de referencia

Comparativa de los proyectos open source evaluados en la primera fase (datos de actividad verificados a mediados de 2026):

| Proyecto | Estrellas | Estado | ¿CPU sin GPU? | Español | Papel en este proyecto |
|---|---|---|---|---|---|
| **pipecat-ai/pipecat** | ~12.700 | Muy activo (v1.x) | Sí (framework) | Sí (según servicios) | **Base elegida**: orquestación tiempo real, barge-in, function calling, 80+ integraciones (Groq, Cerebras, Piper, mem0, Moondream, Silero…). |
| livekit/agents | ~10.500 | Muy activo | Sí (framework) | Sí | Alternativa sólida; WebRTC nativo pero mayor complejidad para un despliegue de un solo servidor. |
| dnhkng/GLaDOS | ~5.400 | Muy activo | Parcial (más lento) | Parcial | Referencia de pipeline de baja latencia y de diseño de personalidad fuerte. |
| KoljaB/RealtimeSTT | ~9.800 | Muy activo | Sí | Sí (Whisper) | Referencia técnica de STT streaming con VAD y wake word. |
| KoljaB/RealtimeTTS | ~3.900 | Muy activo | Sí (Piper/Kokoro) | Sí | Referencia técnica de TTS streaming multimotor. |
| KoljaB/RealtimeVoiceChat | ~3.700 | Pausado | Parcial | Sí | Demo completa STT→LLM→TTS con interrupciones; inspiración, no base. |
| leon-ai/leon | ~17.200 | Transición 2.0 | Sí | Parcial | Asistente por *skills*; documentación incompleta en 2.0. |
| OpenVoiceOS (ex-Mycroft) | ~4.300 | Activo (OVOS) | Sí | Sí | Orientado a *smart speaker*; filosofía privacy-first. |
| mezbaul-h/june | ~800 | Inactivo | Sí | Sí | Stack local simple (Ollama+Whisper+Coqui); sin mantenimiento. |
| vocodedev/vocode-core | ~3.800 | Inactivo | Parcial | Sí | Framework de llamadas telefónicas; descartado. |

**Conclusión**: ningún proyecto "llave en mano" cumple a la vez tiempo real + visión + memoria evolutiva + herramientas + español + CPU-only. La estrategia correcta es **componer** el sistema sobre Pipecat con piezas best-in-class, que es exactamente lo que define este estudio.

---

# 6. Capa de audio: escucha

## 6.1 Palabra de activación: openWakeWord

- **Elección**: modelo preentrenado **"hey jarvis"** de openWakeWord (entrenado con ~200.000 clips sintéticos de la frase y ~31.000 h de datos negativos). Funciona aunque el resto de la conversación sea en español: la palabra de activación es independiente del idioma de uso.
- Consumo: diseñado para CPU modestas (decenas de modelos simultáneos en un core de Raspberry Pi 3); en el i5-10400T, < 5 % de un hilo.
- Alternativas descartadas: Porcupine de Picovoice (wake word custom de pago, ~6.000 $/año el plan que lo permite); microWakeWord (pensado para ESP32, interesante solo si en el futuro se añaden satélites).
- Entrenar una palabra propia ("Jarvis" a secas, u otra) es factible con los notebooks de Colab del proyecto (datos sintéticos); se deja como mejora opcional de la fase 7.

## 6.2 Detección de actividad de voz: Silero VAD

Estándar de facto, integrado nativamente en Pipecat. Parámetro clave: `stop_secs ≈ 0,2` (silencio que marca fin de turno). Es también el disparador del *barge-in*: si el usuario habla mientras Jarvis responde, se cancela TTS y generación.

## 6.3 Transcripción: faster-whisper

| Modelo (CT2, INT8) | RAM | Velocidad en este CPU | Calidad es-ES | Uso recomendado |
|---|---|---|---|---|
| base | ~0,5 GB | Muy rápida | Aceptable | Solo si hiciera falta recortar. |
| **small** | ~1 GB | Más rápido que tiempo real | Buena | **Punto de partida.** |
| medium | ~2 GB | Cerca de tiempo real en frases cortas | Muy buena | Subir si small comete errores. |
| large-v3-turbo | ~1,5 GB | Sorprendentemente viable en INT8 | Excelente | Probar en fase de ajuste; cabe en RAM. |

Notas: `faster-whisper` (CTranslate2) es 4× más rápido que el Whisper original a igual precisión y rinde aún más con cuantización INT8 en CPU. Whisper es multilingüe nativo: transcribe español de España sin configuración especial (`language="es"` fija el idioma y ahorra la detección).

## 6.4 Audio headless en Ubuntu Server

El servidor no tiene escritorio, así que el audio se gestiona por ALSA puro:

1. Identificar dispositivos: `arecord -l` (micrófono) y `aplay -l` (salida).
2. Pasar el dispositivo a los contenedores con `devices: ["/dev/snd:/dev/snd"]` y `group_add: ["audio"]`.
3. Si en el futuro varios procesos necesitan el micro a la vez, instalar PipeWire en el host y compartir el socket; para un único orquestador, ALSA directo es más simple y con menos latencia.
4. Con un dispositivo de conferencia con AEC por hardware, la cancelación de eco queda resuelta sin software adicional (la alternativa software —módulo AEC de PipeWire/WebRTC— añade complejidad y CPU).

---

# 7. Síntesis de voz en español

## 7.1 Requisito y marco legal

El usuario desea una voz masculina elegante en castellano, evocadora del doblaje de J.A.R.V.I.S., **sin clonar la voz de un actor real**. Clonar la voz de una persona identificable sin consentimiento vulnera el RGPD (la voz es dato personal/biométrico; las infracciones de principios básicos alcanzan multas de hasta 20 M€ o el 4 % de la facturación global), el derecho a la propia imagen (LO 1/1982 en España) y las obligaciones de etiquetado de voz sintética del AI Act europeo. Las vías legales son: voces con licencia abierta entrenadas con datos consentidos, licenciar una voz comercial, o clonar la propia voz del usuario.

## 7.2 Catálogo Piper en español y elección

| Voz | Variante | Calidad | Género | Veredicto |
|---|---|---|---|---|
| **es_ES-davefx-medium** | España | medium (22,05 kHz) | Masculina | **ELEGIDA**: mejor equilibrio naturalidad/latencia en castellano; licencia MIT. |
| es_ES-sharvard-medium | España | medium | A verificar escuchando | Candidata alternativa. |
| es_ES-carlfm-x_low | España | x_low | Masculina | Calidad insuficiente (existe build comunitario "high" en HF: friyin/vits-piper-es_ES-carlfm-high). |
| es_ES-mls_9972 / mls_10246 | España | low | — | Descartadas. |
| es_MX-claude-high | México | high | Masculina | La de más fidelidad del set, pero acento mexicano. |

Muestras escuchables en el reproductor oficial: `https://rhasspy.github.io/piper-samples/`. Modelos en `https://huggingface.co/rhasspy/piper-voices` (carpeta `es/`). Existen además decenas de voces comunitarias en español (repositorios de HirCoir y otros), con una salvedad: la licencia de HirCoir prohíbe su uso en servicios de pago (el uso personal está permitido).

**Importante**: el repositorio original `rhasspy/piper` fue archivado en octubre de 2025; el desarrollo continúa en el fork **OHF-Voice/piper1-gpl** (Open Home Foundation). Usar ese fork (o los contenedores Wyoming mantenidos) garantiza compatibilidad futura; las voces `.onnx` existentes siguen funcionando.

## 7.3 Comparativa de motores TTS en CPU

| Motor | Naturalidad ES | Latencia en este CPU | Local | Veredicto |
|---|---|---|---|---|
| **Piper (davefx)** | Buena | RTF ≈ 0,2 → primera frase < 200 ms | Sí | **Principal.** |
| Edge-TTS (es-ES-AlvaroNeural) | Excelente | Cientos de ms–2 s (red) | No | **Fallback opcional**: endpoint no oficial de Microsoft, gratuito pero sin garantías; tratar como extra, jamás como dependencia crítica. |
| Kokoro-82M (voces `em_*`) | Español en preview, irregular en frases cortas | < 0,3 s típica | Sí | Auditar más adelante; no para el arranque. |
| XTTS-v2 (Coqui) | Muy alta (clonación) | 10–30 s/frase sin GPU | Sí | Inviable en CPU; licencia CPML no comercial. |
| F5-TTS / OuteTTS / Orpheus | Altas | Pensados para GPU | Sí | Inviables en tiempo real sobre esta CPU. |

## 7.4 Voz propia en el futuro (opcional)

Si más adelante se desea una voz única: entrenar/afinar una voz Piper en español usando una GPU puntual en la nube (Colab gratuito sirve; existen notebooks oficiales y guías de la comunidad) a partir de un dataset con licencia o grabaciones propias, y **ejecutar la voz resultante en la CPU del M70q** (la inferencia Piper es trivial). Esto mantiene el principio local-first: la GPU solo se usa una vez para entrenar.

---

# 8. El cerebro: LLM externo ultrarrápido

## 8.1 Por qué externo

Medido en CPUs equivalentes, un 7–8B Q4 genera ~3–4 tok/s (una respuesta de 60 tokens tardaría 15–20 s) y los modelos pequeños rápidos (0,5–3B) no sostienen ni la calidad ni la personalidad requeridas. La inferencia especializada en la nube invierte la ecuación: el primer token llega antes de que Piper pueda empezar a hablar.

## 8.2 Comparativa de proveedores (verificado 2026)

| Proveedor | Modelo de referencia | Velocidad | TTFT | Precio /M tokens (in/out) | Free tier |
|---|---|---|---|---|---|
| **Groq** (LPU) | llama-3.3-70b-versatile | ~276–400 tok/s (hasta ~1.200 en modelos ligeros) | **< 100 ms, el más consistente** | $0,59 / $0,79 | 30 RPM · 6.000 TPM · ~1.000 req/día (14.400 en llama-3.1-8b-instant) |
| **Cerebras** (WSE-3) | llama-3.3-70b | ~1.800–2.500 tok/s (picos 4.000 con decodificación especulativa) | 80–150 ms | ~$0,60–3,90 según modelo | ~30 RPM · ~1.000 req/día en 70B |
| Gemini 2.5 Flash / Flash-Lite | — | Alto | ~0,4 s | Muy bajo | Generoso |
| GPU clásica (referencia) | — | 50–200 tok/s | 400–600 ms | — | — |

Ambos líderes convierten el LLM en un no-cuello-de-botella del pipeline de voz. Matiz relevante: el propio equipo de mem0 ejecuta sus operaciones de memoria sobre Groq y reporta una reducción de latencia de ~5×, lo que valida la sinergia Groq+mem0 de este diseño.

## 8.3 Decisión y enrutado

- **Principal**: Groq `llama-3.3-70b-versatile` (calidad GPT-4o-class en conversación, español excelente, function calling soportado).
- **Failover**: Cerebras (mismo modelo) → Gemini 2.5 Flash. Implementado con **LiteLLM** como proxy local: un único endpoint OpenAI-compatible para Pipecat, con *retries*, *fallbacks* y presupuesto configurables en YAML.
- **Optimización de coste**: el *prompt caching* de Groq es automático y los tokens cacheados cuestan el 50 % **y no computan para los rate limits** — con un system prompt largo (personalidad + memorias), esto extiende mucho el free tier. Si aparecen errores 429 sostenidos, subir al tier Developer (~10× límites) o derivar tráfico a Gemini.
- **Coste mensual estimado** (uso doméstico, 30–60 min/día de conversación): free tier de Groq probablemente suficiente; en el peor caso, pocos euros (p. ej., ~1,4 M tokens/mes ≈ 1–2 €).

## 8.4 Modo emergencia offline

Contenedor Ollama con **Qwen 2.5 3B instruct** (o equivalente vigente) apagado por defecto; LiteLLM lo usa como último recurso. Expectativas honestas: respuestas correctas pero básicas, ~5–10 tok/s; suficiente para "enciende la luz" o "qué hora es", no para conversación rica.

---

# 9. Memoria y aprendizaje continuo

## 9.1 Modelo de memoria multinivel

| Tipo | Contenido | Implementación |
|---|---|---|
| Trabajo | Conversación en curso | Contexto de Pipecat (agregadores). |
| Episódica | Qué pasó y cuándo ("el martes me dijiste que…") | mem0 con metadatos temporales + log de conversaciones en SQLite. |
| Semántica | Hechos y preferencias del usuario | mem0 (vector store Chroma) + perfil markdown. |
| Procedimental | Cómo comportarse ("no me des listas por voz") | Ficha de personalidad + reglas extraídas en la reflexión nocturna. |
| Relacional | Bromas internas, hitos, nivel de confianza | Categoría propia en mem0; alimenta la evolución de la personalidad. |

## 9.2 Comparativa de sistemas de memoria

| Sistema | Arquitectura | Self-hosted CPU | Integración con Pipecat | Observaciones |
|---|---|---|---|---|
| **mem0 OSS** | Vector (+grafo en cloud de pago) | **Sí** (`local_config` con Chroma) | **Nativa** (`Mem0MemoryService`) | ~48k estrellas; extracción automática de hechos con operaciones añadir/actualizar/borrar/ignorar; huella de contexto mínima (~1,8k tokens). **Elegido.** |
| Zep / Graphiti | Grafo de conocimiento temporal | Sí, pero requiere Neo4j | Manual | Mejor en razonamiento temporal (LongMemEval ~64–71 % vs ~49 % de mem0), a costa de una infraestructura pesada para 16 GB compartidos. |
| Letta (ex-MemGPT) | "SO de agente" con memoria por niveles | Sí | Sustituiría a Pipecat como runtime | Potente (sleep-time compute), pero acopla todo el proyecto a su framework. |
| LangMem | SDK de LangChain | Sí | Manual | Solo si el proyecto viviera en LangGraph. |

**Configuración elegida**: mem0 OSS en modo local con Chroma como vector store y **embedder HuggingFace explícito** (por defecto mem0 usaría OpenAI: hay que fijarlo). Modelo de embeddings: `intfloat/multilingual-e5-small` (multilingüe, ~120 M parámetros, rápido en CPU, excelente en español); alternativa de más calidad: BGE-M3 (más pesado). El LLM que mem0 usa internamente para extraer hechos también apunta a Groq vía LiteLLM.

## 9.3 Reflexión nocturna y perfil evolutivo (el "aprender e iterar")

La memoria automática por turno no basta para *aprender*; se añade un proceso de consolidación inspirado en los *Generative Agents* de Stanford y en el *sleep-time compute* de Letta:

1. **Cron a las 04:00**: un script recopila las conversaciones del día (log SQLite) y las envía a Groq con el prompt `prompts/reflection_nightly.md`, que pide: hechos nuevos consolidados, contradicciones con memorias previas (y su resolución), patrones de comportamiento del usuario, momentos relevantes para la relación, y propuestas de ajuste de comportamiento.
2. El resultado actualiza: (a) memorias mem0 (vía API local), (b) `persona/perfil_usuario.md` (perfil evolutivo, versionado en git → cada cambio queda auditado con diff), y (c) opcionalmente `persona/relacion.md` (hitos, bromas internas, nivel de confianza).
3. **Decaimiento y poda**: las memorias no reforzadas pierden prioridad de recuperación; un job semanal archiva las obsoletas.

¿Fine-tuning periódico con las conversaciones? Descartado deliberadamente: la práctica consolidada en 2025-2026 es que la personalización vía memoria+prompt es más controlable, reversible, auditable y barata que reentrenar pesos, y este hardware tampoco podría entrenar localmente.

## 9.4 Privacidad de la memoria

Las memorias viven en `data/chroma` y `data/mem0` (SSD local), entran en el backup cifrado de restic y **nunca** se suben a ningún servicio. Al LLM solo viajan las 5–10 memorias relevantes por turno, como texto dentro del prompt.

---

# 10. Personalidad

## 10.1 Diseño en tres capas

1. **Ficha estática versionada** (`persona/jarvis.md`): identidad, valores, tono, límites y reglas de voz. Es el "carácter" estable.
2. **Estado relacional dinámico** (`persona/relacion.md` + memorias de categoría "relación"): evoluciona con la reflexión nocturna. Es lo que hace que en el mes 6 existan bromas internas y referencias compartidas.
3. **Reglas de voz** (críticas para TTS): frases cortas; nada de listas, emojis ni markdown; números y horas en palabras; una pregunta como máximo; ironía ligera mejor que párrafos.

## 10.2 Ficha de personalidad base (resumen del system prompt en español)

```text
Eres JARVIS, el asistente personal de [NOMBRE]. Hablas castellano de España.

CARÁCTER: ingenioso, leal, sereno. Humor seco y elegante, nunca payaso.
Británicamente cortés, con confianza creciente según vuestra historia.
Jamás servil: si [NOMBRE] se equivoca, se lo dices con tacto y datos.

VOZ (tus respuestas se leen en voz alta):
- Frases cortas. Sin listas, sin emojis, sin formato.
- Números, horas y unidades en palabras.
- Máximo una pregunta por turno, y solo si hace falta.
- Si la respuesta es larga, da primero lo esencial y ofrece ampliar.

CONTEXTO: recibirás memorias de conversaciones pasadas y un perfil de
[NOMBRE]. Úsalos con naturalidad, como quien recuerda, sin citarlos como
"según mis datos". Si no recuerdas algo, lo admites sin dramatismo.

HERRAMIENTAS: dispones de acciones (n8n), búsqueda y lectura web, y cámara.
Úsalas cuando aporten; anuncia brevemente lo que vas a hacer si tardará.

LÍMITES: nada de inventar hechos; en temas médicos/legales/financieros das
información y recomiendas profesionales; reconoces tus errores con humor.
```

## 10.3 Consistencia y evolución

- La ficha cambia **solo** por commit manual del usuario (control total); el estado relacional cambia solo por la reflexión nocturna (cambios pequeños, auditables por diff).
- Anti-deriva: la reflexión nunca reescribe el carácter base; un test mensual de regresión (10 preguntas fijas) permite comparar respuestas y detectar derivas de tono.

---

# 11. Visión y presencia proactiva

## 11.1 Veredicto

**Sí a la presencia proactiva**, porque puede hacerse barata: el truco es no ejecutar nunca inferencia continua, sino un pipeline escalonado donde cada etapa solo se activa si la anterior da positivo, y descargar la detección a la iGPU.

## 11.2 Pipeline escalonado

```
Webcam (V4L2) → 1) Detección de movimiento (OpenCV, diferencia de frames)   ~0 % CPU, siempre activo
                 2) ¿Movimiento? → 1 frame a YOLOv8n/11n INT8 con OpenVINO  ~15 ms en la iGPU UHD 630
                 3) ¿Persona? → reconocimiento facial de 1 frame             (InsightFace/MediaPipe, CPU puntual)
                 4) ¿Es [NOMBRE] y llevaba >30 min fuera? → evento a Pipecat → "Bienvenido a casa, señor."
```

Reglas anti-pesadez: histéresis (no saludar dos veces en X minutos), franjas horarias, y modo "no molestar" conmutables desde el panel.

## 11.3 Decisiones de hardware/software de visión

| Opción | Veredicto | Motivo |
|---|---|---|
| OpenVINO sobre iGPU UHD 630 | **Usar** | ~15 ms por inferencia de detección; libera la CPU; ya está en el equipo. |
| Frigate | No (de momento) | Excelente NVR, pero sobredimensionado para una única webcam local; un servicio Python propio integra mejor con Pipecat. Reconsiderar si se añaden cámaras IP. |
| Coral USB TPU | **No comprar** | Drivers abandonados por Google (solo mantenimiento comunitario); la propia documentación de Frigate ya no lo recomienda para instalaciones nuevas. |
| Reconocimiento facial | CompreFace (servicio Docker) o InsightFace embebido | Para 1–3 personas de la casa, InsightFace embebido en el servicio de presencia es más ligero; CompreFace si se quiere UI de gestión de caras. |

## 11.4 Visión bajo demanda ("Jarvis, ¿qué ves?")

- Capturar 1 frame y enviarlo al **LLM con visión vía API**: en Groq, `meta-llama/llama-4-scout-17b-16e-instruct` (acepta imágenes; ojo: el catálogo de modelos de Groq rota —Maverick fue retirado en marzo de 2026—, verificar el vigente al implementar). Alternativa: Gemini 2.5 Flash.
- **Moondream local queda descartado para interacción** (carga de 30–90 s y latencia alta en CPU); solo serviría para análisis en lote nocturnos.
- Privacidad: el frame solo sale del servidor cuando el usuario lo pide explícitamente o cuando una automatización lo requiere y así se ha configurado.

## 11.5 Coste total en reposo

Wake word + VAD + detección de movimiento simultáneos: **~5–10 % de CPU** estimado. Compatible con todo lo demás.

---

# 12. Herramientas y acciones: integración con n8n

## 12.1 Arquitectura de las acciones

n8n se ejecuta **en el mismo servidor** como contenedor, y cada automatización se expone como un **webhook HTTP local**. En Pipecat, cada acción se registra como una *function/tool* del LLM; cuando el modelo decide usarla, el handler hace un `POST` a `http://n8n:5678/webhook/...` por la red interna de Docker (sin salir a internet) y devuelve el resultado al contexto, que fluye con naturalidad al TTS.

```
Usuario: "Jarvis, apunta que mañana recoja el paquete"
  → LLM (Groq) decide llamar a la tool crear_recordatorio(texto, fecha)
  → Pipecat ejecuta el handler → POST http://n8n:5678/webhook/recordatorio
  → n8n: workflow (validación → Todoist/Notion/Telegram/lo que sea) → respuesta JSON
  → LLM redacta: "Hecho. Mañana te recordaré lo del paquete."
```

Ventaja clave: **añadir capacidades sin tocar el código del asistente**. Crear un workflow nuevo en la UI de n8n + declarar la tool (nombre, descripción, parámetros) en un YAML del orquestador = nueva habilidad de Jarvis.

## 12.2 Registro de tools en Pipecat (patrón)

Pipecat soporta function calling de forma transversal: se definen los esquemas (formato estándar) y se registran handlers con `llm.register_function(...)` (o `register_direct_function`); las llamadas y sus resultados quedan integrados automáticamente en el contexto de la conversación.

```python
from pipecat.adapters.schemas.function_schema import FunctionSchema
import aiohttp, os

N8N = os.getenv("N8N_BASE", "http://n8n:5678")
SECRET = os.getenv("N8N_WEBHOOK_SECRET")

tool_recordatorio = FunctionSchema(
    name="crear_recordatorio",
    description="Crea un recordatorio o tarea para el usuario",
    properties={
        "texto": {"type": "string", "description": "Qué recordar"},
        "fecha": {"type": "string", "description": "Fecha/hora ISO o lenguaje natural"},
    },
    required=["texto"],
)

async def crear_recordatorio(params):  # handler
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{N8N}/webhook/recordatorio",
                          json=params.arguments,
                          headers={"X-Jarvis-Secret": SECRET}) as r:
            await params.result_callback(await r.json())

llm.register_function("crear_recordatorio", crear_recordatorio)
```

(Identico patrón para `domotica_*`, `enviar_mensaje`, `estado_servidor`, etc. El catálogo de tools vive en `config/tools.yaml` y el panel permite activarlas/desactivarlas.)

## 12.3 Despliegue de n8n en este servidor

Datos verificados de los requisitos 2026: la RAM es el cuello de botella de n8n (2 GB se considera el mínimo práctico; cada ejecución con payload grande puede consumir 150–300 MB), y **PostgreSQL es la base de datos recomendada desde el día uno** (SQLite se bloquea con webhooks concurrentes y migrar después es tedioso). Para el uso personal de Jarvis (decenas de ejecuciones/día, payloads pequeños), una asignación de ~1–1,5 GB para n8n + ~0,3 GB para PostgreSQL es holgada.

Configuración esencial: fijar versión de imagen (nada de `latest` con auto-update), `N8N_ENCRYPTION_KEY` (cifra credenciales guardadas), `WEBHOOK_URL` correcta, y exponer la UI **solo** en la interfaz de Tailscale. Seguridad de los webhooks: cabecera secreta (`X-Jarvis-Secret`) validada en el primer nodo del workflow, y red interna de Docker para el tráfico Pipecat→n8n.

## 12.4 MCP como evolución (opcional)

n8n incorpora desde 2025 nodos de **MCP (Model Context Protocol)**, y Pipecat también soporta MCP. A futuro, exponer los workflows como herramientas MCP eliminaría la declaración manual de esquemas. Para la v1, los webhooks simples son más depurables y suficientes.

---

# 13. Navegación por internet nativa

## 13.1 Estrategia de doble vía

**Vía A (principal, local-first): SearXNG self-hosted + lector de páginas como tools del LLM.**

- **SearXNG** es un metabuscador open source que agrega 70+ motores (Google, Bing, Brave, Wikipedia, GitHub…) y expone una **API JSON** ideal para agentes: ilimitada, gratuita, privada y sin API keys. Despliegue: contenedor oficial + Redis para caché/limitación.
- Configuración crítica para uso como API: añadir `json` a `formats` en `settings.yml` (causa del clásico error 403 si falta) y, para un único usuario local, desactivar el *limiter*.
- **Tool `web_search(query)`**: consulta `http://searxng:8080/search?q=...&format=json`, devuelve los 5 mejores resultados (título, URL, snippet).
- **Tool `web_read(url)`**: descarga la página y extrae el texto principal con `trafilatura` (Python, local), troceado a un máximo de tokens. Con ambas tools, el LLM "navega": busca → elige → lee → sintetiza, citando la fuente de viva voz.

**Vía B (atajo gestionado): sistemas Compound de Groq.**

- `groq/compound` y `groq/compound-mini` añaden al modelo **búsqueda web integrada (con tecnología Tavily) y ejecución de código del lado del servidor**: una sola llamada API resuelve "¿qué ha pasado hoy con X?" sin infraestructura propia. `compound-mini` hace una única llamada a herramienta por petición con ~3× menos latencia que `compound`.
- Coste: se paga el modelo subyacente + las herramientas (orientativo 2026: búsqueda básica ~5 $/1.000 peticiones, avanzada ~8 $/1.000, visitar página ~1 $/1.000).
- **Limitación decisiva**: los sistemas Compound **no admiten tools personalizadas del usuario** → no pueden ser el modelo principal de Jarvis (perderíamos n8n). 

**Diseño final**: el modelo principal (`llama-3.3-70b`) lleva las tools propias (`n8n_*`, `web_search`, `web_read`, `ver_camara`). El enrutador puede derivar a `groq/compound-mini` consultas puramente informativas de actualidad como optimización opcional. La Vía A garantiza, además, que la capacidad de buscar no depende de ningún proveedor.

## 13.2 Recencia y veracidad

Regla en el system prompt: para hechos posteriores a su corte de conocimiento o cambiantes (precios, noticias, marcadores), Jarvis **debe** usar `web_search` antes de afirmar; y al responder de viva voz, menciona la fuente brevemente ("según El País de esta mañana…").

---

# 14. Centro de control web

## 14.1 Papel del panel

La voz va siempre por el micro/altavoz USB del servidor (latencia mínima); el panel es el **centro de mando** del sistema, accesible desde el navegador (PC o móvil) **únicamente vía Tailscale**. No hay nada off-the-shelf que cubra memorias+persona+tools+latencias de un stack tan personalizado, así que se diseña un panel propio ligero (FastAPI + frontend simple), complementado por las UIs ya incluidas en las piezas (n8n, y opcionalmente Grafana).

## 14.2 Funcionalidades del panel (v1)

| Sección | Contenido | Fuente de datos |
|---|---|---|
| **Dashboard** | Estado de servicios (healthchecks), CPU/RAM/temperatura, últimas interacciones | Docker API + psutil + log SQLite |
| **Conversación en vivo** | Transcripción en tiempo real (usuario y Jarvis), botón "interrumpir", envío de texto manual | WebSocket del orquestador |
| **Latencias** | Desglose por etapa (wake→STT→LLM→TTS) por turno, percentiles, gráfico histórico | Métricas del pipeline (Pipecat expone observabilidad; se persisten en SQLite) |
| **Memorias** | Buscar/ver/editar/borrar memorias de mem0; ver el perfil evolutivo y su historial git | API local de mem0 + git |
| **Personalidad** | Editor de `persona/jarvis.md` con commit a git y recarga en caliente | git + endpoint reload |
| **Herramientas** | Activar/desactivar tools (n8n, web, cámara), ver últimos usos y resultados | `config/tools.yaml` + log |
| **Presencia** | Conmutar modo no-molestar, ver últimos eventos de presencia, franjas horarias | Servicio vision |
| **Sistema** | Logs por servicio, lanzar backup manual, ver estado del failover LLM | Docker logs + restic + LiteLLM |

## 14.3 Implementación

- **Backend**: FastAPI (mismo lenguaje que todo el stack), con WebSocket para el directo y SQLite (`data/logs/events.db`) como almacén de eventos/métricas (cada etapa del pipeline emite un evento con timestamps).
- **Frontend**: una SPA mínima (HTMX o React+Vite servida estática). Móvil-first: el caso de uso típico es mirar el panel desde el sofá.
- **Autenticación**: el panel solo escucha en la IP de Tailscale; aun así, sesión con contraseña (defensa en profundidad).
- **Complementos**: la **UI de n8n** (`:5678`) es ya el editor visual de las acciones; **Grafana+Prometheus** queda como opcional de fase avanzada (Langfuse self-hosted se descarta de inicio: su stack v3 —ClickHouse, Redis, Postgres, S3— es desproporcionado para 16 GB compartidos).

---

# 15. Instalación completa desde cero

## 15.1 Instalación de Ubuntu Server 24.04 LTS

1. Descargar la ISO LTS desde ubuntu.com y grabarla en USB (balenaEtcher/Rufus). Arrancar el M70q desde USB (F12).
2. Idioma/teclado español. Activar **OpenSSH server** en el instalador. No instalar snaps adicionales.
3. **Particionado manual con los dos discos**:
   - **NVMe 256 GB** (el rápido): EFI 1 GB · `/` ext4 ~80 GB · resto a `/var/lib/docker` ext4. Aquí viven SO, imágenes y modelos (lo sensible a latencia de carga).
   - **SSD 1 TB**: una única partición ext4 montada en `/srv/jarvis` (datos persistentes: memoria, logs, backups, n8n, descargas).
   - Sin swap en disco (se usará zram).
4. Crear usuario, importar llave SSH si la pides en el instalador, reiniciar.

## 15.2 Post-instalación (bloque de comandos)

```bash
# Actualización y básicos
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git curl htop alsa-utils v4l-utils zram-tools cpufrequtils

# zram en lugar de swap en disco (mejor latencia con 16 GB)
echo -e "ALGO=zstd\nPERCENT=50" | sudo tee /etc/default/zramswap
sudo systemctl restart zramswap

# Gobernador de CPU para latencia (TDP 35 W: el coste energético es bajo)
echo 'GOVERNOR="performance"' | sudo tee /etc/default/cpufrequtils
sudo systemctl restart cpufrequtils

# Verificar audio y vídeo
arecord -l        # anota card/device del micrófono USB
aplay -l          # anota la salida (altavoz)
v4l2-ctl --list-devices   # webcam → /dev/video0

# Docker + Compose
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker,audio,video $USER && newgrp docker

# Seguridad base
sudo apt install -y ufw fail2ban
sudo ufw default deny incoming && sudo ufw allow OpenSSH && sudo ufw enable
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl restart ssh

# Tailscale (acceso remoto privado al panel y a n8n)
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

## 15.3 Despliegue del proyecto

```bash
sudo mkdir -p /srv/jarvis && sudo chown $USER /srv/jarvis
cd /srv/jarvis && git clone <tu-repo> . 
cp .env.example .env          # rellenar: GROQ_API_KEY, CEREBRAS_API_KEY, GEMINI_API_KEY,
                              # N8N_ENCRYPTION_KEY, N8N_WEBHOOK_SECRET, PANEL_PASSWORD…
bash scripts/download_models.sh   # piper davefx · faster-whisper small int8 · hey_jarvis.onnx ·
                                  # yolov8n OpenVINO · multilingual-e5-small
docker compose up -d --build
docker compose logs -f orchestrator   # primera conversación de prueba
sudo cp systemd/jarvis.service /etc/systemd/system/ && sudo systemctl enable jarvis
```

---

# 16. Estructura del repositorio

```
jarvis/
├── docker-compose.yml          # Orquestación completa (ver §17)
├── .env / .env.example         # Secretos (no versionado) / plantilla
├── config/
│   ├── litellm/config.yaml     # Groq→Cerebras→Gemini, reintentos, presupuesto
│   ├── tools.yaml              # Catálogo de tools (n8n, web, cámara) y su estado on/off
│   ├── searxng/settings.yml    # formats: [html, json]; limiter off (uso local)
│   └── audio/asound.conf       # Dispositivos ALSA por nombre estable
├── services/
│   ├── orchestrator/           # Pipecat: bot.py, tools/, transports, Dockerfile
│   ├── vision/                 # presence.py (OpenCV→OpenVINO→cara), Dockerfile
│   ├── panel/                  # FastAPI + frontend del centro de control
│   └── reflection/             # Job nocturno de consolidación de memoria
├── prompts/
│   ├── system_jarvis.md        # Núcleo del system prompt (se compone con persona/)
│   └── reflection_nightly.md   # Prompt de la reflexión nocturna
├── persona/
│   ├── jarvis.md               # Ficha de personalidad (editable desde el panel, commit git)
│   ├── perfil_usuario.md       # Perfil evolutivo (lo escribe la reflexión)
│   └── relacion.md             # Hitos, bromas internas, confianza
├── data/                       # En SSD 1TB; NO versionado
│   ├── models/ · chroma/ · mem0/ · n8n/ · postgres/ · logs/ · backups/
├── scripts/
│   ├── download_models.sh · backup.sh · prewarm.sh · healthcheck.sh
├── systemd/jarvis.service
└── docs/ (ARCHITECTURE.md · RUNBOOK.md · este estudio)
```

# 17. docker-compose maestro (resumen funcional)

```yaml
name: jarvis
services:
  litellm:        # Proxy LLM unificado con failover Groq→Cerebras→Gemini
    image: ghcr.io/berriai/litellm:main-stable        # fijar versión concreta
    volumes: ["./config/litellm/config.yaml:/app/config.yaml:ro"]
    env_file: .env
    command: ["--config","/app/config.yaml","--port","4000"]

  chroma:         # Vector store de la memoria
    image: chromadb/chroma:<versión>
    volumes: ["/srv/jarvis/data/chroma:/chroma/chroma"]

  searxng:        # Buscador propio (API JSON)
    image: searxng/searxng:<versión>
    volumes: ["./config/searxng:/etc/searxng:ro"]
    depends_on: [redis]
  redis:
    image: redis:alpine

  postgres:       # BD de n8n (recomendada frente a SQLite)
    image: postgres:16-alpine
    environment: [POSTGRES_DB=n8n, POSTGRES_USER=n8n, POSTGRES_PASSWORD=${N8N_DB_PASS}]
    volumes: ["/srv/jarvis/data/postgres:/var/lib/postgresql/data"]

  n8n:            # Motor de acciones (webhooks)
    image: n8nio/n8n:<versión-fijada>
    environment:
      - DB_TYPE=postgresdb
      - N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}
      - WEBHOOK_URL=http://n8n:5678/
    ports: ["100.x.x.x:5678:5678"]      # SOLO IP de Tailscale
    volumes: ["/srv/jarvis/data/n8n:/home/node/.n8n"]
    depends_on: [postgres]

  orchestrator:   # Pipecat: oídos, cerebro (vía litellm), voz, tools
    build: ./services/orchestrator
    devices: ["/dev/snd:/dev/snd"]
    group_add: ["audio"]
    volumes:
      - /srv/jarvis/data/models:/models
      - ./prompts:/prompts:ro
      - ./persona:/persona:ro
      - ./config:/config:ro
      - /srv/jarvis/data/logs:/logs
    environment: [LLM_BASE=http://litellm:4000, SEARX=http://searxng:8080,
                  N8N_BASE=http://n8n:5678, WHISPER_MODEL=small,
                  PIPER_VOICE=es_ES-davefx-medium]
    depends_on: [litellm, chroma, searxng, n8n]

  vision:         # Presencia (movimiento→persona→cara) en iGPU
    build: ./services/vision
    devices: ["/dev/video0:/dev/video0", "/dev/dri/renderD128:/dev/dri/renderD128"]
    environment: [OPENVINO_DEVICE=GPU, DETECT_FPS=2]

  panel:          # Centro de control
    build: ./services/panel
    ports: ["100.x.x.x:8080:8080"]      # SOLO IP de Tailscale
    volumes: ["/srv/jarvis/data/logs:/logs", "./persona:/persona", "./config:/config",
              "/var/run/docker.sock:/var/run/docker.sock:ro"]
    depends_on: [orchestrator]
```

(Todas las imágenes con versión fijada, `restart: unless-stopped` y healthcheck; el archivo completo con todos los detalles se entrega en el repositorio.)

# 18. Presupuestos del sistema

## 18.1 RAM (16 GB totales)

| Servicio | RAM estimada |
|---|---|
| Ubuntu Server + Docker | ~1,2–1,5 GB |
| faster-whisper small INT8 | ~1 GB (medium: ~2 GB) |
| Piper (davefx) | ~0,15 GB |
| openWakeWord + Silero VAD | ~0,2 GB |
| Pipecat + tools + LiteLLM | ~0,7 GB |
| mem0 + embeddings e5-small | ~0,5 GB |
| Chroma | ~0,3–0,5 GB |
| n8n + PostgreSQL | ~1,3–1,8 GB |
| SearXNG + Redis | ~0,3–0,4 GB |
| Vision (OpenCV+OpenVINO) | ~0,3 GB |
| Panel (FastAPI) | ~0,15 GB |
| **TOTAL** | **~6–7 GB** → margen de ~9 GB |

## 18.2 Latencia por turno (objetivo)

| Etapa | Tiempo |
|---|---|
| Wake word | 50–150 ms |
| Fin de turno (VAD) | ~200 ms |
| STT (frase corta, small INT8) | 400–1.200 ms |
| LLM Groq (primer token, red España incluida) | 200–600 ms |
| TTS Piper (primer audio) | < 200 ms |
| **Percibido hasta que Jarvis empieza a hablar** | **~1,3–2,0 s** (optimizable hacia ~1 s) |

Optimizaciones aplicadas: streaming extremo a extremo, síntesis por frases, prompt caching de Groq, keep-alive HTTP, prewarming de modelos al arranque, `stop_secs` agresivo. Si una herramienta tardará (n8n lento, web), Jarvis lo anuncia ("dame un segundo…") para que la espera sea natural.

## 18.3 Coste mensual

| Concepto | Estimación |
|---|---|
| LLM (Groq, uso doméstico) | 0–5 € (free tier + caching; ~1–2 € si se pagara todo) |
| Búsquedas web | 0 € (SearXNG propio) — o céntimos si se usa compound-mini |
| Visión bajo demanda | céntimos (frames puntuales) |
| Electricidad (35 W TDP, 24/7) | ~3–5 € |
| **Total** | **< 10 €/mes** |

# 19. Seguridad, backups y acceso remoto

- **Red**: ufw deny-all entrante salvo SSH; panel y n8n ligados solo a la IP de Tailscale; nada expuesto a internet; tráfico interno por la red de Docker.
- **SSH**: solo llaves; fail2ban activo.
- **Secretos**: `.env` fuera de git (plantilla `.env.example`); opcional sops-age para versionarlos cifrados; `N8N_ENCRYPTION_KEY` cifra las credenciales de n8n.
- **Webhooks**: cabecera secreta validada en el primer nodo de cada workflow.
- **Backups**: `scripts/backup.sh` con **restic** (cron diario 05:00, tras la reflexión): `data/chroma`, `data/mem0`, `data/n8n`, `data/postgres` (dump), `persona/`, `prompts/`, `config/`, `.env` → repositorio restic cifrado en disco externo o destino remoto. Prueba de restauración mensual.
- **Actualizaciones**: deliberadas (`docker compose pull` manual con versiones fijadas); **sin** watchtower automático (Pipecat 1.x y n8n introducen breaking changes; leer changelogs).
- **Privacidad**: audio/vídeo nunca salen; al LLM solo texto (y frames bajo demanda explícita); logs locales con rotación.

# 20. Hoja de ruta por fases

| Fase | Contenido | Criterio de éxito |
|---|---|---|
| 0. Base (sem. 1) | Ubuntu, particionado, zram, seguridad, Tailscale, Docker | SSH por llaves, `docker run hello-world`, micro y cámara detectados |
| 1. Oídos y voz (sem. 2) | openWakeWord + VAD + faster-whisper + Piper davefx en Pipecat | "Hey Jarvis" → transcribe → responde eco por el altavoz |
| 2. Cerebro (sem. 3) | LiteLLM (Groq→Cerebras→Gemini) + personalidad v1 + barge-in | Conversación natural < 2 s con interrupciones |
| 3. Memoria (sem. 4) | mem0+Chroma+e5 local, reflexión nocturna, perfil en git | Recuerda hechos entre sesiones; el perfil se actualiza solo |
| 4. Acciones e internet (sem. 5) | n8n+Postgres, 2–3 workflows, SearXNG + web_read | "Apunta X" crea la tarea; "¿qué ha pasado hoy con Y?" busca y cita |
| 5. Presencia y visión (sem. 6) | Servicio vision (OpenVINO iGPU) + ver_camara() | Saluda al llegar (con histéresis); describe la escena bajo demanda |
| 6. Centro de control (sem. 7) | Panel FastAPI completo + métricas de latencia | Todo administrable desde el móvil vía Tailscale |
| 7. Refinamiento (continuo) | Voz custom Piper (Colab), wake word propia, MCP, Grafana, modo offline Qwen, domótica vía n8n | — |

# 21. Riesgos y umbrales de decisión

| Riesgo | Mitigación / Umbral |
|---|---|
| Rotación de modelos en Groq (p. ej., Maverick retirado en 2026) | LiteLLM abstrae el modelo; revisar deprecations al implementar; alias de modelo en config. |
| Free tier insuficiente (429 frecuentes) | Prompt caching; tier Developer; derivar a Gemini. Umbral: >5 fallos/día. |
| Eco acústico arruina el barge-in | Micrófono/altavoz de conferencia con AEC hardware (decisión de compra prioritaria). |
| Pipecat 1.x breaking changes | Versiones fijadas; leer guía de migración antes de subir. |
| Whisper small falla en español coloquial | Subir a medium o large-v3-turbo INT8 (cabe en RAM). Umbral: >1 error grave/10 frases. |
| Edge-TTS deja de funcionar | Es solo fallback; Piper es el principal. |
| CPU de visión sube | Bajar DETECT_FPS; histéresis mayor; apagar presencia desde el panel. Umbral: >30 % sostenido. |
| Deriva de personalidad | La reflexión no toca la ficha base; test mensual de regresión; git diff de persona/. |
| Pérdida de memoria | restic diario cifrado + prueba de restauración mensual. |

# 22. Referencias y recursos

**Frameworks y orquestación**: Pipecat — github.com/pipecat-ai/pipecat · docs.pipecat.ai (function calling, Mem0MemoryService, PiperTTSService, SmallWebRTC) · LiteLLM — github.com/BerriAI/litellm.

**Audio**: faster-whisper — github.com/SYSTRAN/faster-whisper · Silero VAD — github.com/snakers4/silero-vad · openWakeWord — github.com/dscripka/openWakeWord (docs/models/hey_jarvis.md).

**Voz**: Piper voces — huggingface.co/rhasspy/piper-voices · muestras — rhasspy.github.io/piper-samples · fork mantenido — github.com/OHF-Voice/piper1-gpl · Edge-TTS — github.com/rany2/edge-tts · Kokoro — huggingface.co/hexgrad/Kokoro-82M.

**LLM**: Groq — console.groq.com/docs (models, pricing, rate limits, deprecations, compound, built-in tools/web search) · Cerebras — cerebras.ai (inference) · Gemini — ai.google.dev.

**Memoria**: mem0 — github.com/mem0ai/mem0 · docs.mem0.ai (embedders HuggingFace, local config) · Zep/Graphiti — github.com/getzep/graphiti · Letta — github.com/letta-ai/letta · Embeddings — huggingface.co/intfloat/multilingual-e5-small · BAAI/bge-m3.

**Visión**: Ultralytics YOLO + OpenVINO — docs.ultralytics.com · OpenVINO — docs.openvino.ai · Frigate (referencia iGPU/Coral) — docs.frigate.video · InsightFace — github.com/deepinsight/insightface · CompreFace — github.com/exadel-inc/CompreFace.

**Acciones e internet**: n8n — docs.n8n.io (self-hosting, webhooks, MCP) · SearXNG — github.com/searxng/searxng (settings.yml, API JSON) · trafilatura — github.com/adbar/trafilatura.

**Infraestructura**: Ubuntu Server — ubuntu.com/server/docs · restic — restic.net · Tailscale — tailscale.com · sops — github.com/getsops/sops.

*Las cifras de rendimiento y precios corresponden a fuentes públicas verificadas entre 2025 y junio de 2026 y deben revalidarse en las páginas oficiales en el momento de implementar cada fase.*
