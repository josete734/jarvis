# Verificación de APIs del esqueleto (11-jun-2026)

Auditoría del código del esqueleto contra el **código fuente real** de cada
librería (tags concretos en GitHub, no solo documentación). Hecha antes de
ejecutar nada en hardware, para reducir los `TODO(Fase 1)`.

## Correcciones aplicadas

| Archivo | Problema detectado | Corrección | Fuente |
|---|---|---|---|
| `services/orchestrator/bot.py` | `PipelineParams(allow_interruptions=True)` — el campo se **eliminó** en Pipecat 1.0; habría roto el arranque (validación Pydantic) | `PipelineTask(Pipeline(...))` sin ese param (interrupciones activas por defecto) | `pipecat@v1.3.0/pipeline/...` |
| `services/orchestrator/bot.py` | `PiperTTSService(voice=...)` — `voice` no es kwarg del servicio embebido | `PiperTTSService(settings=PiperTTSSettings(voice=...), download_dir=/models/piper)` | `services/piper/tts.py`, `services/settings.py` |
| `services/orchestrator/stt_factory.py` | `Model.LARGE_V3` no existe en el enum | `Model.LARGE` (su valor es `"large-v3"`) | `services/whisper/stt.py` |
| `services/orchestrator/stt_factory.py` | `language="es"` (str) — el parámetro es un enum | `language=Language.ES` (`pipecat.transcriptions.language`) | `services/whisper/stt.py` |
| `services/orchestrator/requirements.txt` | extra `silero` está **vacío** en 1.3.0 (el VAD corre sobre el `onnxruntime` base) | quitado del grupo de extras; `openwakeword` va aparte | `pipecat@v1.3.0/pyproject.toml` |
| `services/orchestrator/memory.py` | el taint guard estaba declarado pero sin implementar | override de **`_store_messages`** (único método que escribe en mem0); retrieve intacto | `services/mem0/memory.py` |
| `services/vision/presence.py` | `_person_detected` usaba fórmula de **YOLOv5** (`out[...,4]*out[...,5]`); YOLO11 es `[1,84,2100]` = 4 bbox + 80 clases con sigmoide, **sin objectness**; faltaba **BGR→RGB** | post-proceso v11 correcto en numpy (transpone, clase 0 = `preds[:,4]`, umbral `PERSON_CONF`) | ultralytics #18754, #20712, #9912 |
| `services/vision/presence.py` | `FaceAnalysis` sin `providers` explícito (podía intentar CUDA) | `providers=["CPUExecutionProvider"]` | insightface #2344 |
| `scripts/download_models.sh` | carpeta de export YOLO mal (`..._int8_openvino_model`) | nombre real `yolo11n_openvino_model/` | docs.ultralytics export |
| `scripts/download_models.sh` | asumía auto-descarga de `buffalo_sc` | `buffalo_sc` **NO** se auto-descarga (sí `buffalo_l`/`antelopev2`); intento + nota de descarga manual | insightface README (tabla de packs) |

## Confirmado CORRECTO (sin cambios)

- Rutas e imports de Pipecat: `LocalAudioTransport`/`LocalAudioTransportParams`
  (campos heredados de `TransportParams`), `SileroVADAnalyzer`+`VADParams(stop_secs=0.2)`,
  `LLMContext`, `LLMContextAggregatorPair`+`LLMUserAggregatorParams(vad_analyzer=...)`
  (el VAD va aquí, no en el transport), `FunctionSchema`/`ToolsSchema`,
  `register_function(name, handler, timeout_secs=, cancel_on_interruption=)`,
  frames (`InputAudioRawFrame.audio`, `TranscriptionFrame.text`, `TTSSpeakFrame`),
  `FrameProcessor`/`FrameDirection`, `OpenAILLMService`/`OpenAISTTService(base_url=)`.
- openWakeWord 0.6.0: `Model(wakeword_models=[ruta.onnx], inference_framework="onnx",
  vad_threshold=0.5)`; la key de `predict()` coincide con `models.keys()` para hey_jarvis;
  `download_models` baja también melspectrogram/embedding/silero.
- mem0 1.x: config local `vector_store`(chroma host/port) + `embedder`(huggingface
  `model_kwargs`) + `llm`(openai `openai_base_url`) válida; `add()` hace 2 llamadas LLM.
- InsightFace: `normed_embedding` está L2-normalizado (coseno = producto escalar);
  `app.get()` espera BGR (no convertir, al revés que YOLO).

## TODO genuinos (solo se validan ejecutando o con cuenta propia)

- Conexión de mem0 1.x a Chroma server vía `Settings` legacy: si falla con la versión
  de `chromadb` instalada, usar el campo `client=chromadb.HttpClient(...)` (fallback).
- e5 en mem0 1.x aplica el mismo prefijo `"query: "` a add y search (subóptimo, funcional).
- Umbral `PERSON_CONF` y `MATCH_THRESHOLD`: calibrar con la cámara real (Fase 5).
- `insightface==1.0.1`: confirmado en PyPI en una verificación previa; si el pin diera
  guerra, relajar a `insightface>=1.0,<2`.
- Los puntos abiertos de `PLAN_FINAL.md §13` (tag de litellm, patch de n8n, límites de
  Gemini, TPD del Developer tier, modelo de visión vigente, puerto de parakeet, sintaxis
  de `tailscale serve`).

*Tags verificados: pipecat-ai@v1.3.0, openWakeWord@v0.6.0, mem0ai@v1.0.11, y código
fuente de ultralytics e insightface (main).*

---

## Oleada de cierre (11-jun-2026, ronda final)

Tras una revisión adversarial (lentes corrección/seguridad/operaciones + verificación
escéptica de cada hallazgo) se corrigieron 15 hallazgos confirmados:

| Severidad | Corrección |
|---|---|
| HIGH | Wake word: los modelos compartidos (melspectrogram/embedding/silero_vad) se hornean en el Dockerfile del orquestador — antes el gate crasheaba al arrancar buscándolos en el paquete vacío. |
| HIGH | Confirmación verbal: `user_just_affirmed` rechaza cualquier frase con negación (fail-closed) aunque contenga "vale/sí/ok" — antes "no, no vale la pena" autorizaba. Quitado "si" sin tilde; tests de exploit añadidos. |
| MEDIUM | `litellm` healthcheck con `python3` (la imagen wolfi no trae curl); parakeet healthcheck por `/dev/tcp`. |
| MEDIUM | Gate de wake word: `TranscriptWatcher` renueva el keepalive al hablar (antes se dormía a los 45 s a mitad de conversación). |
| MEDIUM | Panel fail-closed (allowlist vacía = denegar) + servidor de eventos con secreto compartido (`EVENTS_SECRET`) en `/dnd` y `/event/presence`. |
| MEDIUM | SSRF: la validación de IP pasa al resolver de aiohttp (cierra el TOCTOU/DNS-rebinding). |
| MEDIUM | Reflexión nocturna: ventana de 24 h (antes solo veía 00:00-04:00 → perdía el día). |
| MEDIUM | n8n: anti-replay (dedupe de request-id en staticData) en el workflow de ejemplo. |
| LOW | mem0 history.db persistido (`/srv/jarvis/mem0`); htmx vendorizado; `restic`+`unzip` en install_host; `buffalo_sc` con descarga sha256; RUNBOOK de caras actualizado; `-T` en runs por stdin; systemd reflection con `-T`. |

Datos verificados aplicados: tags fijados (litellm `v1.88.1`, n8n `2.26.2`, searxng datado),
parakeet `0.5.0-int8` en `:5092` (`STT_BASE_URL` corregido), `chromadb==1.5.9` (la config
host/port de mem0 1.x usa el mismo path que `HttpClient` y habla la API v2 del server 1.5.9).
Implementados los huecos: logging de conversación (`user_said`/`assistant_said`, que la
reflexión necesita) y `enroll_face.py`. Warmup descartado (Whisper/Piper cargan eager,
verificado). 37 tests en verde.
