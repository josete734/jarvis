---
name: debug-voice-pipeline
description: >-
  Úsala para diagnosticar problemas del pipeline de voz: no oye, no responde, no
  detecta "hey jarvis", corta al usuario, se interrumpe a sí mismo, latencia alta,
  errores de STT/LLM/TTS. Diagnóstico por etapas con comandos concretos.
---

# Depurar el pipeline de voz

Sigue el flujo en orden: **audio → wake word → VAD/turnos → STT → LLM → TTS → barge-in**.
Logs: `make logs s=orchestrator`.

## 1. Audio (entrada/salida)
- `make list-audio` → confirma índices; fíjalos en `.env` (`AUDIO_INPUT_INDEX/OUTPUT_INDEX`).
- ¿El contenedor ve el micro? El servicio monta `/dev/snd` y va en grupo `audio`.
- Prueba cruda en el host: `arecord -d 3 t.wav && aplay t.wav`.

## 2. Wake word ("hey jarvis" no despierta o se dispara solo)
- Logs del gate: busca `Wake word detected (score=...)`.
- Umbral: `WAKE_THRESHOLD` (def. 0.5). Sube si hay falsos positivos, baja si no detecta.
- `WAKE_FRAMEWORK=onnx` (recomendado en x86). Modelo en `/models/openwakeword/`.
- Si se dispara con su propia voz → es problema de AEC (ver §6), no del umbral.

## 3. VAD y turnos (corta al usuario / espera demasiado)
- smart-turn v3.2 es el árbitro de fin de turno por defecto (no lo desactives).
- Si corta cuando José piensa: NO subas `stop_secs` a ciegas; revisa que smart-turn
  está activo y su `stop_secs` de fallback (3 s).
- `stop_secs=0.2` es el default correcto de Pipecat 1.x.

## 4. STT (transcribe mal o lento)
- v1: faster-whisper `small` INT8 (`WHISPER_MODEL`). Sube a `medium`/`large-v3-turbo`
  si falla en español coloquial (>1 error grave/10 frases).
- Fase 2-3: parakeet vía `STT_BACKEND=openai` + `make parakeet-on`. Comprueba que
  `stt-parakeet` responde y el puerto coincide con `STT_BASE_URL`.

## 5. LLM (no responde, tarda, ignora tools)
- Logs de litellm: `make logs s=litellm`. ¿Llega a Groq? ¿salta al failover?
- `tool_use_failed` o bucles → típico de `gpt-oss-120b` con ≥3 tools: descripciones
  de tools más explícitas o vuelve a `llama-3.3-70b` (1 línea en litellm/config.yaml).
- 429 sostenidos → ¿Developer tier activado? (el free tier 100K TPD se agota pronto).

## 6. TTS y barge-in
- Piper: voz `es_ES-davefx-medium` en `/models/piper/`. ¿Primer audio < 200 ms?
- **Se interrumpe a sí mismo** = AEC insuficiente. Re-ejecuta `bash scripts/test_aec.sh <device>`.
  Si el delta RMS > 6 dB, aplica plan B (PipeWire echo-cancel) o C (livekit-rtc APM):
  PLAN_FINAL §5.2.

## Latencia por turno (objetivo)
~1,3-2,0 s en v1; ~0,9-1,5 s con parakeet. Si se dispara, mira qué etapa: STT
(modelo grande), LLM (failover lento / sin Developer tier) o TTS (Piper frío → prewarm).
