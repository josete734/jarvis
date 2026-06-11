# Construir un "Jarvis" doméstico en un ThinkCentre M70q (i5-10400T, 16GB, sin GPU): investigación y arquitectura recomendada

## TL;DR
- **El hardware (i5-10400T, 16GB RAM, sin GPU) NO puede ejecutar bien la pieza pesada — el LLM y la visión — en local; la arquitectura ganadora es HÍBRIDA**: wake word + STT + TTS locales en el Tiny, y LLM + visión en la nube vía API. Como atajo de máxima calidad y mínimo esfuerzo, una alternativa 100% cloud con la **OpenAI Realtime API** o **Gemini Live** da la conversación más natural con barge-in real.
- **El mejor punto de partida open source es el framework Pipecat** (orquestación de voz/visión en tiempo real, 12.715 estrellas en GitHub bajo licencia BSD-2-Clause, con 131 contribuidores y soporte para 83 servicios/modelos/APIs, muy activo) combinado con **RealtimeSTT/RealtimeTTS** de KoljaB; para algo más "llave en mano" tipo Jarvis está **dnhkng/GLaDOS** (5,4k estrellas, pipeline de baja latencia con interrupciones y visión opcional).
- **Coste cloud estimado**: una conversación híbrida con LLM por texto (Claude/GPT) cuesta **céntimos al mes** en uso doméstico; una solución 100% speech-to-speech ronda **$0,18–$0,50 por llamada/hora de conversación activa** (Gemini Live es drásticamente más barato que OpenAI Realtime en audio).

## Key Findings

### 1. Qué es realista en este hardware
El i5-10400T es una CPU de 6 núcleos / 12 hilos de bajo consumo (TDP 35W) con gráficos Intel UHD 630, sin núcleos tensoriales ni VRAM. Esto define tres realidades:
- **STT (Whisper)**: viable en CPU con modelos pequeños. `faster-whisper` (CTranslate2, INT8) transcribe ~3 min de audio en ~60s con el modelo *medium* en un CPU de 8 vCPU; con *small*/*base* es cómodamente más rápido que tiempo real. Es la pieza local más sólida.
- **TTS (Piper)**: perfecto para CPU. Modelos de 10–80 MB, generación en tiempo real, con voces nativas en español (España y México).
- **LLM**: aquí está el cuello de botella. Modelos 7–8B cuantizados Q4 en CPU dan **~3–4 tokens/s** (Mistral/Llama 8B), demasiado lento para conversación natural. Modelos 0.5–3B sí corren rápido (Qwen 0.6B ~34 tok/s, Phi-4 mini ~7 tok/s) pero su calidad conversacional es pobre. **Conclusión: el LLM debe ir a la nube.**
- **Visión (VLM)**: Moondream 2 (2B) y SmolVLM (256M–2.2B) corren en CPU pero lentos (segundos por imagen). Para "ver al usuario" de forma ocasional es aceptable; para visión continua conviene cloud.

### 2. Proyectos open source comparados

**Tabla 1 — Proyectos de asistente/voz (datos junio 2026)**

| Proyecto | Estrellas | Actividad | Lenguaje | CPU sin GPU | Español | Notas |
|---|---|---|---|---|---|---|
| **pipecat-ai/pipecat** | 12.715 | Muy activo (v1.1.0 abr 2026) | Python | Sí (framework) | Sí (vía STT/TTS/LLM elegidos) | Orquestador voz+visión en tiempo real, interrupciones, multi-agente. 131 contribuidores, 83 servicios soportados. **La mejor base.** |
| **livekit/agents** | ~10,5k | Muy activo (1.5.x may 2026) | Python | Sí (framework) | Sí | WebRTC nativo, modo `console` local, escalable. Curva WebRTC más dura. |
| **dnhkng/GLaDOS** | 5,4k | Muy activo (2026) | Python | Parcial ("works without GPU, just slower") | Parcial (LLM/TTS configurable) | Pipeline <600ms objetivo, barge-in, VLM opcional, MCP. Personalidad Portal. |
| **KoljaB/RealtimeSTT** | 9,8k | Muy activo (v1.0.0 may 2026) | Python | **Sí** (faster-whisper) | Sí (Whisper multilingüe) | Librería STT con VAD, wake word. Pieza clave. |
| **KoljaB/RealtimeTTS** | 3,9k | Muy activo (v0.7.3 may 2026) | Python | **Sí** (Piper/Kokoro/System) | Sí | Contraparte TTS, streaming, múltiples motores. |
| **KoljaB/RealtimeVoiceChat** | 3,7k | Pausado (autor lo dejó) | Python | Parcial (CUDA recomendada) | Sí | Demo web completa STT→LLM→TTS con interrupciones. Buena referencia. |
| **leon-ai/leon** | 17,2k | En transición a 2.0 | TypeScript/Python | Sí | Parcial | Asistente modular por skills. 2.0 en preview, docs incompletas. |
| **mezbaul-h/june** | 784 | Inactivo (ago 2024) | Python | Sí (`device: cpu`) | Sí (XTTS) | Ollama+Whisper+Coqui local. Simple pero sin mantenimiento. |
| **vocodedev/vocode-core** | 3,8k | Inactivo (jun 2024, busca mantenedores) | Python | Parcial | Sí | Framework de llamadas; menos recomendable hoy. |
| **OpenVoiceOS / Mycroft** | ~4,3k (mycroft-core) | Mycroft muerto; OVOS activo | Python | Sí | Sí | Privacidad-first; orientado a smart speaker/HA. |
| **Willow** | — | DIY ESP32 | C | N/A (satélite hw) | Limitado | Hardware satélite ESP32-S3-BOX; necesita servidor inferencia. |

**Tabla 2 — Componentes del stack**

| Componente | Opción local (CPU) | Opción cloud | Recomendación para este hardware |
|---|---|---|---|
| **Wake word** | openWakeWord (2,2k★, diseñado para CPU; 15-20 modelos en 1 core de RPi3), microWakeWord | Picovoice Porcupine ($6.000/año plan Starter para custom) | **openWakeWord** local (gratis, soporta "Hey Jarvis" prediseñado) |
| **STT** | faster-whisper (23,3k★, CPU INT8) modelo small/medium; Vosk | Deepgram, OpenAI gpt-4o-transcribe (~$0,006/min), Google | **faster-whisper small/medium** local; cloud si quieres mínima latencia |
| **LLM** | Qwen/Llama 3B (rápido pero flojo), 8B (~3-4 tok/s, lento) | Claude Sonnet 4.6 ($3/$15 MTok), GPT, Gemini Flash | **Cloud** (Claude/Gemini); local 3B solo como fallback offline |
| **TTS** | Piper (CPU, voces ES), Kokoro (82M, ES en preview multilingüe) | ElevenLabs, OpenAI TTS ($15/M chars = $0,015/1K chars; gpt-4o-mini-tts ~$0,015/min), Gemini TTS | **Piper** (ES nativo, rápido); Kokoro si quieres voz más natural |
| **Visión / VLM** | Moondream 2 (2B), SmolVLM (256M-2.2B) en CPU, lento | Claude/GPT-4o vision, Gemini | **Cloud** para descripción de escena; Moondream local para uso ocasional |
| **Reconocimiento facial** | CompreFace (Apache 2.0, CPU/Docker, 99,7% LFW con InsightFace; hasta 99,83% InsightFace-ArcFace, 99,65% FaceNet), Double Take, face_recognition | AWS Rekognition | **CompreFace** local (CPU con AVX, Docker) |
| **Orquestación tiempo real** | Pipecat, LiveKit Agents | Pipecat Cloud, LiveKit Cloud | **Pipecat** (vendor-neutral, Python, soporta motores locales y cloud) |

### 3. Costes cloud estimados (uso doméstico)

- **OpenAI Realtime API (speech-to-speech)**: tarifa oficial de OpenAI — "Audio input is priced at $100 per 1M tokens and output is $200 per 1M tokens. This equates to approximately $0.06 per minute of audio input and $0.24 per minute of audio output". Una conversación de voz-in/voz-out paga ambos: en pruebas reales de Skywork.ai (oct-2025, 4 min de voz de usuario + 1 min de IA) "Per-call ≈ $0.50 ... adding VAD and shortening closing spiels cut audio-out by ~20%, dropping per-call to ≈ $0.45"; CallSphere (11 perfiles modelados, 2026) sitúa el coste "between $0.18 and $0.46 per minute, with caching pulling it under $0.25". Para uso doméstico de ~15 min/día activos, del orden de **$30–$60/mes**.
- **Gemini Live API**: tarifa Gemini 2.5 Flash (ai.google.dev) — entrada de audio $0,30/1M tokens y salida $0,40/1M tokens en tier de pago; a 32 tokens/s de audio equivale a ~$0,0006/min de entrada de audio, sustancialmente más barato que OpenAI. Uso doméstico: **del orden de pocos euros al mes**.
- **Arquitectura híbrida (STT/TTS local + LLM por texto)**: solo pagas tokens de texto del LLM. Con Claude Sonnet 4.6 ($3 input / $15 output por millón) o Gemini Flash, una conversación doméstica típica cuesta **céntimos a pocos euros al mes**. Es la opción más barata con buena calidad.

### 4. Hardware adicional recomendado
- **Micrófono**: el punto más crítico para barge-in y far-field. **ReSpeaker USB 4-Mic Array (XVF3000/XVF3800)** con AEC, beamforming y supresión de ruido por hardware — evita los bucles de "se oye a sí misma". Alternativa de presupuesto: cualquier micro con cancelación de eco o auriculares.
- **Webcam**: cualquier webcam USB UVC 1080p sirve para Moondream/CompreFace.
- **Altavoz**: altavoz USB/jack decente; idealmente conferencia con AEC.
- **Acelerador**: un **Coral TPU USB** acelera detección de objetos/caras (Frigate) pero NO ejecuta LLMs ni la mayoría de VLMs. El iGPU Intel UHD 630 puede acelerar visión vía OpenVINO. Si en el futuro quieres LLM/visión local de verdad, lo eficiente es una GPU NVIDIA externa (eGPU) o un mini-PC con NPU — pero para empezar, **no compres acelerador; usa cloud para LLM/visión**.

## Details

### Sistema operativo y plataforma
Recomendación: **Debian 12 o Ubuntu Server 24.04 LTS bare metal + Docker Compose**. Razones:
- Máximo rendimiento de CPU para Whisper/Piper (sin overhead de virtualización).
- Docker aísla cada servicio (wake word, STT, TTS, orquestador, CompreFace).
- Proxmox es válido si quieres snapshots y separar otros servicios del homelab, pero añade overhead que en un hardware ya justo no conviene para las cargas de IA.

Contenedores sugeridos: `faster-whisper-server` (API OpenAI-compatible), `piper` (o wyoming-piper), `openWakeWord`, `compreface`, y el orquestador (Pipecat) como app Python o contenedor propio.

### Arquitectura recomendada (híbrida)
```
Micrófono (ReSpeaker) → openWakeWord (local) → faster-whisper small/medium (local)
   → [texto] → LLM en la nube (Claude Sonnet / Gemini Flash) ← contexto de visión
                                  ↓
Cámara → frame on-demand → VLM cloud (GPT-4o/Gemini) o Moondream local
                                  ↓
   respuesta texto → Piper TTS (local, voz ES) → Altavoz
   (barge-in: VAD local corta el TTS al detectar voz del usuario)
CompreFace (local) → reconoce quién habla → personaliza el system prompt
```
Esta arquitectura mantiene local todo lo barato y sensible a latencia (escucha, transcripción, voz), y delega a la nube solo el razonamiento y la visión compleja. Pipecat orquesta el pipeline y gestiona interrupciones.

### Alternativa 100% local (expectativas realistas)
Posible pero con compromisos: wake word + faster-whisper small + Piper funcionan bien; el LLM tendría que ser un 3B (Qwen2.5 3B / Llama 3.2 3B) con calidad limitada y ~5-10 tok/s. La latencia de respuesta total rondaría 3-6s y las respuestas serían básicas. Sirve como modo offline de respaldo, no como experiencia principal.

### Alternativa 100% cloud (máxima naturalidad)
OpenAI Realtime API o Gemini Live gestionan STT+LLM+TTS en una sola conexión WebSocket/WebRTC con barge-in nativo y latencia <1s. El Tiny solo captura audio/vídeo y reproduce. Es la vía más rápida a un "Jarvis" que conversa de verdad; el coste es la única pega (especialmente OpenAI).

## Recommendations

**Fase 0 — Preparación (formateo)**
1. Instalar Debian 12 / Ubuntu Server 24.04 LTS. Instalar Docker + Docker Compose.
2. Conectar y verificar ReSpeaker (mic) y webcam (`arecord -l`, `v4l2-ctl --list-devices`).

**Fase 1 — Voz básica (turnos, push-to-talk o wake word)**
3. Levantar `faster-whisper-server` (modelo `small` ES) y `piper` (voz `es_ES`).
4. Script Python: wake word (openWakeWord "Hey Jarvis") → STT → llamada a Claude/Gemini API (texto) → Piper. **Claude puede escribir este script y el docker-compose completo.**

**Fase 2 — Tiempo real con interrupciones (barge-in)**
5. Migrar el pipeline a **Pipecat**: VAD (Silero) + STT streaming + LLM streaming + TTS por frases, con cancelación de TTS al detectar voz. Probar también la **OpenAI Realtime / Gemini Live** como backend speech-to-speech para comparar naturalidad.

**Fase 3 — Visión**
6. Añadir captura de cámara on-demand: al pedir "¿qué ves?", enviar frame a un VLM cloud (Gemini/GPT-4o) o a Moondream local. Integrar **CompreFace** para reconocer al usuario y personalizar respuestas.

**Fase 4 — Expansiones**
7. Memoria (vector DB), herramientas (MCP), y **domótica vía Home Assistant** (Pipecat y GLaDOS ya soportan integración HA) cuando se desee.

**Umbrales de decisión:**
- Si la latencia local de STT supera ~1,5s con `small`, baja a `base`.
- Si el coste de OpenAI Realtime supera tu presupuesto, cambia a híbrido (LLM por texto) o a Gemini Live.
- Si quieres LLM/visión 100% local con calidad, el detonante de compra es una GPU NVIDIA ≥8-12GB VRAM; sin ella, mantén cloud.

## Cómo puede ayudarte Claude en la implementación
Claude (este asistente) puede entregarte directamente: el `docker-compose.yml` con faster-whisper-server + piper + openWakeWord + CompreFace; el script de orquestación Python de la Fase 1; la migración a una pipeline Pipecat completa con barge-in; los `.env` con la configuración de claves API; scripts de instalación bash desde cero; y los prompts de sistema en español para personalizar el asistente. Basta con pedir cada pieza por fase.

## Caveats
- Las cifras de tokens/segundo en CPU varían según cuantización, hilos y longitud de contexto; los ~3-4 tok/s para 8B y ~34 tok/s para Qwen 0.6B provienen de pruebas de terceros, no de este equipo exacto. Conviene benchmarkear con `ollama --verbose`.
- Los precios de APIs cambian con frecuencia; las cifras (OpenAI Realtime $0,06/$0,24 por min; Gemini 2.5 Flash audio $0,30/$0,40 por 1M tokens; Claude Sonnet $3/$15; OpenAI TTS $15/M chars) son de finales 2025–mediados 2026 y deben verificarse en las páginas oficiales antes de presupuestar.
- Soporte de español: Whisper y Piper lo manejan bien; Kokoro tiene español en preview multilingüe (su entrenamiento es principalmente inglés), así que valida la calidad antes de adoptarlo como TTS principal.
- Picovoice Porcupine ofrece wake word en español pero su plan custom es caro ($6.000/año); openWakeWord es gratis pero sus modelos prediseñados son solo en inglés (el wake word en inglés "Hey Jarvis" funciona aunque hables español).
- Varios proyectos populares están inactivos (june, vocode-core, openWakeWord sin releases desde 2024); priorizar los mantenidos (Pipecat, LiveKit, RealtimeSTT/TTS, GLaDOS, faster-whisper).
- KoljaB/RealtimeVoiceChat es excelente referencia pero su autor pausó el mantenimiento y recomienda CUDA; úsalo como inspiración, no como base de producción.

## Enlaces a recursos clave
- Pipecat: github.com/pipecat-ai/pipecat — Docs: pipecat.ai
- LiveKit Agents: github.com/livekit/agents
- GLaDOS: github.com/dnhkng/GLaDOS (y fork con vision KokoDOS: github.com/kaminoer/KokoDOS)
- RealtimeSTT / RealtimeTTS / RealtimeVoiceChat: github.com/KoljaB/...
- faster-whisper: github.com/SYSTRAN/faster-whisper
- Piper TTS (voces y samples): rhasspy.github.io/piper-samples ; voces ES en Hugging Face (rhasspy/piper-voices, HirCoir para ES)
- openWakeWord: github.com/dscripka/openWakeWord
- Kokoro: huggingface.co/hexgrad/Kokoro-82M
- Moondream: moondream.ai ; SmolVLM: huggingface.co/blog/smolvlm
- CompreFace: github.com/exadel-inc/CompreFace ; Double Take: github.com/jakowenko/double-take
- Leon: github.com/leon-ai/leon
- Precios: openai.com/api/pricing ; ai.google.dev/gemini-api/docs/pricing ; platform.claude.com/docs (pricing)
- Hardware: ReSpeaker (seeedstudio.com), Coral TPU (coral.ai)