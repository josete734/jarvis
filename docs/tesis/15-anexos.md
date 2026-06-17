# Anexos {.unnumbered}

## Anexo A. Stack tecnológico y versiones

El sistema se despliega como un conjunto de servicios contenedorizados con Docker Compose y versiones fijadas. La tabla resume los componentes principales y su función.

| Componente | Función | Tecnología |
|---|---|---|
| Orquestador | Pipeline de voz y agente multicanal | Pipecat (Python) |
| Pasarela LLM | Interfaz única + *failover* | LiteLLM |
| Cerebro | Razonamiento (texto) | LLM en la nube vía la pasarela |
| Wake word | Palabra de activación | openWakeWord (ONNX) |
| STT | Reconocimiento de voz | faster-whisper *small* INT8 |
| TTS | Síntesis de voz | Piper (`es_ES-davefx-medium`) |
| VAD / fin de turno | Detección de actividad y turno | Silero VAD + *smart-turn* |
| Memoria | Episódica y de hechos | SQLite + FTS5 (almacén `facts`) |
| Búsqueda | Metabuscador privado | SearXNG |
| Visión | Presencia y reconocimiento | OpenVINO + YOLO11n + InsightFace |
| Panel / HUD | Centro de control | FastAPI + HTMX |
| Acceso remoto | Exposición segura del panel | Cloudflare Tunnel + Access |
| Acciones | Webhooks-herramienta | n8n (HMAC) |

## Anexo B. Reproducibilidad y operación

El repositorio público contiene el código, la configuración de ejemplo (`.env.example`) y la documentación operativa. La puesta en marcha sigue tres pasos: preparación del host (Docker, audio, cortafuegos, directorios), provisión de secretos en un fichero de entorno excluido del control de versiones, y construcción y arranque de las imágenes con los modelos. El manual de operación (*runbook*) detalla el procedimiento, el diagnóstico de incidencias y las tareas de mantenimiento.

## Anexo C. Honestidad metodológica y estado del proyecto

Este trabajo documenta un sistema en uso real y en evolución. En aras del rigor, se hace explícito el estado de cada subsistema en el momento de la redacción: el pipeline de voz, el razonamiento, la memoria, la proactividad, la multicanalidad y la agencia segura están **implementados y verificados en operación**; el subsistema de visión está **implementado pero inactivo**, a la espera de la integración de la cámara física. Las cifras de rendimiento se etiquetan a lo largo del documento como *medidas* o *estimadas* según corresponda. El código está cubierto por una suite de 68 pruebas automáticas.

## Anexo D. Nota sobre el nombre

El sistema recibe el nombre de J.A.R.V.I.S. como referencia cultural a la figura del mayordomo digital. Por una decisión de diseño documentada, la palabra que activa el asistente por voz es «hey Mycroft» —en alusión a Mycroft Holmes—, ya que el modelo de detección correspondiente resultó empíricamente más fiable sobre el hardware empleado. El disparador y el nombre del sistema son, por tanto, independientes.
