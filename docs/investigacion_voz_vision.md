# Jarvis Homelab — Plan de Implementación Definitivo (Parte 3, la definitiva)

## TL;DR
- **Voz:** usa **Piper `es_ES-davefx-medium`** (voz masculina española, licencia MIT, RTF ~0,2 en CPU → <200 ms/frase) como motor TTS principal, con **Edge-TTS `es-ES-AlvaroNeural`** como alternativa de mayor naturalidad cuando haya red. Descarta XTTS-v2 (10–30 s/frase sin GPU, inviable).
- **Presencia proactiva: SÍ, pero barata.** Pipeline escalonado propio (detección de movimiento OpenCV → persona con YOLOv8n sobre la iGPU vía OpenVINO → cara) que consume ~5–10% de CPU en reposo. **NO** uses Frigate (overkill para 1 webcam) ni compres el Coral USB TPU (drivers abandonados por Google). Visión bajo demanda ("¿qué ves?") vía API cloud (Groq Llama 4 Scout / Gemini Flash), nunca con Moondream local.
- **Stack:** Pipecat 1.x (BSD, Python 3.11+) orquestando openWakeWord "hey jarvis" + Silero VAD + faster-whisper small/medium int8 + Piper, LLM Groq `llama-3.3-70b-versatile` vía LiteLLM con fallback Cerebras/Gemini, y memoria mem0 OSS + Chroma + embeddings HuggingFace. Cabe holgado en 16 GB (~4–5 GB de uso). Latencia total esperada ~1,3–2,0 s por turno.

---

## 1. Decisión de voz

### 1.1 Catálogo completo Piper en español (rhasspy/piper-voices)

| Voz | Locale | Calidad | Género | Valoración para "Jarvis" |
|-----|--------|---------|--------|--------------------------|
| **`davefx`** | es_ES | medium (22,05 kHz) | **Masculino** (confirmado: paquete OpenMandriva la describe como *"Spanish male voice for the Piper TTS system"*) | **GANADOR para Castellano.** Mejor equilibrio naturalidad/latencia |
| `sharvard` | es_ES | medium | Sin verificar en fuente primaria | Auditar la muestra antes de decidir |
| `carlfm` | es_ES | x_low (16 kHz) | Masculino | Calidad baja; existe build community "high" de `friyin/vits-piper-es_ES-carlfm-high` (entrenada 170 épocas en RTX 3090, dominio público) |
| `mls_9972` / `mls_10246` | es_ES | low (16 kHz) | — | Calidad insuficiente |
| `claude` | es_MX | **high** (22,05 kHz) | Masculino | Máxima fidelidad del set español, pero **acento mexicano**, no castellano |
| `ald` | es_MX | medium | — | Alternativa mexicana |

**Cómo escuchar muestras:** reproductor interactivo en **https://rhasspy.github.io/piper-samples/** (selecciona Spanish es_ES → voz → calidad). Las muestras se generan del primer párrafo de la entrada de Wikipedia de "rainbow". Los modelos `.onnx`/`.onnx.json` están en `https://huggingface.co/rhasspy/piper-voices/tree/main/es`.

**Voces de la comunidad (HirCoir y otros):** el repositorio `HirCoir/piper-voices` (demo en tts.hircoir.eu.org) ofrece decenas de voces españolas entrenadas (Laura, Elena-v2 argentina, Cortana, etc.). **Atención legal:** la licencia HirCoir prohíbe el uso en servicios de pago (uso personal permitido). También existe `AIHeaven/piper_unofficial_voices` con voces creadas vía el notebook Colab oficial de Piper. Curiosidad: el Space `HirCoir/Piper-TTS-Spanish` incluye un modelo inglés `en_us-jarvis_ucm-high`, pero es en inglés.

### 1.2 Comparativa final de alternativas TTS en CPU

| Motor | Español masculino elegante | Latencia/RTF en CPU | Local | Veredicto |
|-------|----------------------------|---------------------|-------|-----------|
| **Piper `es_ES-davefx-medium`** | Sí (es_ES) | RTF ~0,2 (≈5× tiempo real); primer audio <50 ms; frase corta <200 ms | ✅ | **OPCIÓN ÚNICA RECOMENDADA** |
| Edge-TTS `es-ES-AlvaroNeural` | Sí (es-ES, muy natural) | ~cientos ms a ~2 s (round-trip de red) | ❌ (cloud) | Mejor naturalidad; usar como fallback con red |
| Kokoro-82M `em_alex` / `em_santa` | Sí pero **calidad española sin calificar** y débil en frases <10–20 tokens | <0,3 s; 3–11× tiempo real | ✅ | Auditar; riesgo en comandos cortos |
| XTTS-v2 (Coqui) | Sí (clonación) | **10–30 s/frase** (issue idiap/coqui-ai-TTS #507: *"30 seconds of delay"*) | ✅ | **NO viable sin GPU** + licencia CPML no comercial |
| Sherpa-ONNX (VITS) | Sí (puede ejecutar las propias voces Piper/Kokoro en runtime ONNX) | similar a Piper | ✅ | Alternativa de runtime, no de voz |

**Edge-TTS — fiabilidad/legalidad:** voces `es-ES-AlvaroNeural` (masculino) y `es-ES-ElviraNeural` (femenino). La biblioteca `github.com/rany2/edge-tts` está muy activa (v7.2.7, dic 2025) pero depende del endpoint **no oficial** "read aloud" de Microsoft Edge, que requiere parches frecuentes cuando Microsoft cambia versiones. Es gratis, sin API key, pero requiere internet y es zona legal gris. Útil como fallback de calidad, no como motor principal offline. Se puede exponer como API compatible OpenAI con `travisvn/openai-edge-tts` (Docker, puerto 5050).

### 1.3 Estado legal de clonar la voz de un actor de doblaje real
**No lo hagas.** La voz es dato biométrico/personal bajo el GDPR; entrenar un clon sin consentimiento es infracción. Según el **GDPR Art. 83(5)** (gdpr-info.eu), las infracciones de los principios básicos pueden conllevar *"administrative fines up to 20 000 000 EUR, or in the case of an undertaking, up to 4 % of the total worldwide annual turnover of the preceding financial year, whichever is higher"*. Además, el EU AI Act exige etiquetar la voz sintética y España protege el derecho a la propia imagen (Ley Orgánica 1/1982). **Alternativas legales:** (a) voces con licencia abierta entrenadas con datos consentidos (Piper MIT, Kokoro Apache-2.0); (b) licenciar una voz comercial; (c) clonar **tu propia** voz con consentimiento documentado.

**→ Decisión final de voz: Piper `es_ES-davefx-medium` como principal; Edge-TTS `es-ES-AlvaroNeural` como fallback opcional con red.**

---

## 2. Decisión de visión / presencia proactiva

### 2.1 Coste real en CPU (i5-10400T, 6c/12h, sin GPU)
- **Detección de movimiento** (frame differencing OpenCV): prácticamente 0% CPU. Es el centinela permanente.
- **YOLOv8n en CPU puro:** ~4–7 FPS (referencia LattePanda Mu); con OpenVINO int8 en CPU ~7–9 FPS. A 1–2 FPS bajo demanda el coste es asumible.
- **YOLOv8n int8 + OpenVINO sobre la iGPU UHD 630:** ~15 ms/inferencia (~28–66 FPS de capacidad), dejando la CPU libre. Documentación de Frigate confirma *"Intel HD 630: ~15 ms"* con SSDLite MobileNet v2.
- **MediaPipe face detection / reconocimiento facial puntual:** muy ligero para 1 frame.

### 2.2 Arquitectura de "presencia barata" recomendada
```
[Cámara] → Motion detection OpenCV (siempre activo, ~0% CPU)
   └─ si hay movimiento → 1 frame a YOLOv8n vía OpenVINO en iGPU UHD 630 (~15 ms)
        └─ si hay persona → reconocimiento facial 1 frame (MediaPipe/InsightFace)
             └─ evento "usuario ha llegado" → Jarvis saluda
```
En reposo solo corre el motion detection, así que la presencia añade poco sobre el coste base. La clave es **descargar YOLO a la iGPU vía OpenVINO** y no hacer inferencia continua.

### 2.3 Frigate y Coral — veredictos
- **Frigate:** **overkill** para una sola webcam local (está diseñado para múltiples cámaras RTSP). Su detector OpenVINO sobre UHD 630 funciona bien (~15 ms), pero para 1 webcam un script Python ligero propio integra mejor con Pipecat. Úsalo solo si más adelante añades CCTV.
- **Coral USB TPU (~70 €): NO comprar.** Google ha abandonado los drivers; el gasket driver lo mantiene la comunidad (`feranick/gasket-driver`, builds parcheados para kernels 2026). La propia documentación de Frigate dice que el Coral *"is no longer recommended for new Frigate installations, except in deployments with particularly low power requirements"*. OpenVINO en la iGPU que ya tienes es superior y gratis.

### 2.4 Visión bajo demanda ("¿qué ves?")
- **Groq tiene visión vía API:** `meta-llama/llama-4-scout-17b-16e-instruct` acepta imágenes (`image_url` base64, hasta 5 imágenes, contexto 128K) y sigue vigente. **Atención:** `meta-llama/llama-4-maverick-17b-128e-instruct` fue deprecado — anuncio el 20 feb 2026 y retirada el 9 mar 2026 *"in favor of openai/gpt-oss-120b"* (gpt-oss-120b es solo texto, no visión). Usa **Llama 4 Scout** para visión en Groq y verifica el modelo vigente al implementar.
- **Gemini Flash:** alternativa de visión robusta vía LiteLLM.
- **Moondream local en CPU:** carga inicial de 30–90 s y latencia alta; viable solo para lotes, no para interacción en tiempo real. **Envía el frame a Groq/Gemini, no lo proceses localmente.**

**VEREDICTO:** Presencia proactiva **SÍ**, con pipeline escalonado + OpenVINO en iGPU para detección, y visión bajo demanda vía API cloud. **% CPU total estimado en idle** (wake word + Silero VAD siempre activos + motion detection): **~5–10%**, perfectamente compatible con STT/TTS bajo demanda en los 6 núcleos.

---

## 3. Estructura de carpetas del proyecto (monorepo)

```
jarvis/
├── docker-compose.yml            # Orquestación de todos los servicios
├── .env                          # Secretos NO versionados (Groq/Cerebras/Gemini keys)
├── .env.example                  # Plantilla versionada
├── .sops.yaml                    # (opcional) reglas sops-age para secretos cifrados
├── secrets/
│   └── keys.enc.yaml             # secretos cifrados con sops-age (sí versionable)
├── config/
│   ├── pipecat/
│   │   └── pipeline.yaml         # Configuración del pipeline Pipecat
│   ├── litellm/
│   │   └── config.yaml           # Routing Groq→Cerebras→Gemini, prompt caching
│   ├── wakeword/
│   │   └── hey_jarvis.onnx       # (si se usa custom; o el preentrenado)
│   └── audio/
│       └── asound.conf           # Mapeo ALSA del micro USB / webcam
├── services/
│   ├── orchestrator/             # Código Pipecat (bot.py, transports, etc.)
│   │   ├── bot.py
│   │   ├── personality.py        # Carga la ficha Jarvis
│   │   └── Dockerfile
│   ├── memory/                   # Wrapper mem0 OSS
│   │   ├── memory_manager.py
│   │   └── Dockerfile
│   └── vision/                   # Pipeline de presencia (OpenCV→OpenVINO→cara)
│       ├── presence.py
│       └── Dockerfile
├── prompts/                      # Prompts versionados en git
│   ├── system_jarvis.md          # Personalidad: ingenioso, leal, humor seco
│   └── reflection_nightly.md     # Prompt de consolidación nocturna
├── persona/
│   └── jarvis_profile.yaml       # Ficha de personalidad evolutiva (versionada)
├── data/                         # Volúmenes persistentes (NO versionado, en SSD)
│   ├── models/                   # faster-whisper, piper, openwakeword, yolo
│   ├── chroma/                   # Base vectorial de mem0
│   ├── mem0/                     # history.db de mem0
│   └── logs/
├── scripts/
│   ├── download_models.sh        # Descarga inicial automatizada de modelos
│   ├── backup.sh                 # restic de data/chroma, data/mem0, config/, .env
│   ├── healthcheck.sh
│   └── prewarm.sh                # Precalienta modelos al arranque
├── systemd/
│   └── jarvis.service            # Auto-arranque vía docker compose
├── docs/
│   ├── ARCHITECTURE.md
│   └── RUNBOOK.md
└── README.md
```

**Decisiones de diseño:** modelos descargados van a volúmenes en `data/models/` (SSD 1TB); la memoria Chroma y `history.db` de mem0 en `data/chroma|mem0/`; logs en `data/logs/`; la ficha de personalidad y prompts **sí** se versionan en git (`persona/`, `prompts/`); los secretos van en `.env` (no versionado) o cifrados con **sops-age** en `secrets/` (versionable). Esta estructura sigue el patrón observado en proyectos reales mem0+OSS (separación `src/`, `skills/`, `workspace/`, `config.py`).

---

## 4. Guía de instalación paso a paso

### 4.1 Instalación de Ubuntu Server 24.04 LTS
1. Graba el ISO en USB (Rufus/balenaEtcher). Arranca el ThinkCentre y entra en el instalador.
2. **Particionado (manual):**
   - **NVMe 256GB** (rápido) → SO + Docker + modelos: `/` (ext4, ~80 GB), `/var/lib/docker` (resto). Aquí va lo sensible a latencia (modelos cargados a RAM).
   - **SSD 1TB** → datos persistentes: monta en `/srv/jarvis/data` (memoria Chroma, mem0, logs, backups).
   - Swap: con 16 GB de RAM, configura **zram** (comprimido en RAM) en vez de swap en disco para baja latencia; o swapfile de 4 GB en NVMe como red de seguridad.
3. Instala OpenSSH durante el setup. Crea usuario con llave SSH.

### 4.2 Ajustes post-instalación
```bash
# Gobernador de CPU: performance para baja latencia (o 'schedutil' para equilibrio)
sudo apt install -y cpufrequtils linux-tools-common linux-tools-generic
echo 'GOVERNOR="performance"' | sudo tee /etc/default/cpufrequtils
sudo systemctl restart cpufrequtils

# zram (16 GB RAM)
sudo apt install -y zram-tools
echo -e "ALGO=zstd\nPERCENT=50" | sudo tee /etc/default/zramswap
sudo systemctl restart zramswap

# Identifica el micrófono USB y la webcam
arecord -l        # localiza card/device del micro USB
aplay -l          # localiza salida de audio
v4l2-ctl --list-devices   # localiza /dev/video0 (webcam)

# Docker + Compose
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# añade tu usuario a los grupos de audio y vídeo
sudo usermod -aG audio,video $USER
```

### 4.3 Audio headless en Docker
Para servidor sin escritorio, lo más simple y fiable es pasar el dispositivo ALSA directamente:
```bash
# Test desde un contenedor
docker run --rm --device /dev/snd alpine sh -c "apk add alsa-utils && arecord -l"
```
En los servicios de audio del compose se añade `devices: ["/dev/snd:/dev/snd", "/dev/video0:/dev/video0"]`. Si necesitas que varias apps compartan el micro a la vez, instala PipeWire en el host y comparte el socket (`/run/user/1000/pulse/native`) en vez de `--device`. Para un único orquestador, `--device /dev/snd` (acceso exclusivo) basta.

### 4.4 `docker-compose.yml` de ejemplo (completo)
```yaml
name: jarvis

services:
  litellm:
    image: ghcr.io/berriai/litellm:main-stable
    restart: unless-stopped
    ports: ["4000:4000"]
    volumes:
      - ./config/litellm/config.yaml:/app/config.yaml:ro
    env_file: .env
    command: ["--config", "/app/config.yaml", "--port", "4000"]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4000/health/liveliness"]
      interval: 30s
      timeout: 5s
      retries: 3

  chroma:
    image: chromadb/chroma:latest
    restart: unless-stopped
    volumes:
      - /srv/jarvis/data/chroma:/chroma/chroma
    ports: ["8000:8000"]

  orchestrator:
    build: ./services/orchestrator
    restart: unless-stopped
    depends_on: [litellm, chroma]
    env_file: .env
    devices:
      - "/dev/snd:/dev/snd"          # micrófono USB + salida de audio (ALSA)
    group_add:
      - "audio"
    volumes:
      - /srv/jarvis/data/models:/models
      - ./config:/config:ro
      - ./prompts:/prompts:ro
      - ./persona:/persona:ro
    ports: ["7860:7860"]             # SmallWebRTC / UI
    environment:
      - GROQ_BASE_URL=http://litellm:4000
      - WHISPER_MODEL=small          # int8; sube a medium si la CPU aguanta
      - PIPER_VOICE=es_ES-davefx-medium
      - CHROMA_HOST=chroma
    healthcheck:
      test: ["CMD", "python", "-c", "import socket; socket.create_connection(('localhost',7860),2)"]
      interval: 30s
      timeout: 5s
      retries: 3

  vision:
    build: ./services/vision
    restart: unless-stopped
    devices:
      - "/dev/video0:/dev/video0"    # webcam
      - "/dev/dri/renderD128:/dev/dri/renderD128"   # iGPU UHD 630 (OpenVINO)
    volumes:
      - /srv/jarvis/data/models:/models
    environment:
      - DETECT_FPS=2
      - OPENVINO_DEVICE=GPU
    depends_on: [orchestrator]
```
*(Si prefieres microservicios Wyoming en lugar de STT/TTS embebidos en Pipecat, añade `rhasspy/wyoming-faster-whisper` en :10300 y `rhasspy/wyoming-piper` en :10200; ver §6.)*

### 4.5 Descarga de modelos y arranque
```bash
cp .env.example .env          # rellena GROQ_API_KEY, CEREBRAS_API_KEY, GEMINI_API_KEY
bash scripts/download_models.sh   # piper davefx, faster-whisper small int8, owW hey_jarvis, yolov8n openvino
docker compose up -d --build
docker compose logs -f orchestrator
```

### 4.6 Auto-arranque (systemd)
```ini
# /etc/systemd/system/jarvis.service
[Unit]
Description=Jarvis Assistant
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/srv/jarvis
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```
`sudo systemctl enable --now jarvis.service`. Las `restart: unless-stopped` + healthchecks del compose actúan de watchdog por contenedor.

---

## 5. Consumo estimado de RAM / CPU por servicio

| Servicio | RAM aprox. | CPU en reposo | CPU en actividad |
|----------|-----------|---------------|------------------|
| SO Ubuntu + Docker | ~1,5 GB | bajo | — |
| openWakeWord ("hey jarvis") | <100 MB | ~2–5% (1 hilo) | — |
| Silero VAD | <100 MB | ~1–3% | — |
| Vision (motion OpenCV) | ~200 MB | ~2–4% | pico al detectar |
| faster-whisper small int8 | ~1 GB | 0% | alta (1–2 s por frase) |
| Piper davefx | ~150 MB | 0% | breve por frase |
| mem0 + embeddings HuggingFace | ~500 MB | bajo | pico en add/search |
| Chroma | ~300–500 MB | bajo | bajo |
| Pipecat + Python + LiteLLM | ~600 MB | bajo | bajo |
| **TOTAL** | **~4,5–5 GB** | **~5–10%** | picos < 100% |

Cabe holgado en **16 GB** con >10 GB de margen. Si subes Whisper a `medium int8` (~2 GB) o `large-v3-turbo int8` (~1,5 GB), sigue cabiendo. **Qué recortar si hiciera falta:** baja Whisper a `small`, usa embeddings más pequeños (multilingual-e5-small), y desactiva la presencia visual.

---

## 6. Presupuesto de latencia por etapa (turno completo)

| Etapa | Latencia esperada |
|-------|-------------------|
| Wake word ("hey jarvis") | ~50–150 ms (streaming) |
| Fin de turno (VAD, stops_secs 0,2) | ~200 ms |
| STT faster-whisper small int8 (frase corta) | ~0,4–1,2 s |
| LLM Groq llama-3.3-70b (TTFT, 276 t/s) | ~0,3–0,6 s al primer token |
| TTS Piper davefx (primera frase, RTF ~0,2) | <0,2 s al primer audio |
| **TOTAL percibido (a primer audio)** | **~1,3–2,0 s** |

**Trucos de optimización (todos aplicables):** prompt caching de Groq; **streaming sentence-split a Piper** (sintetiza la primera frase mientras el LLM sigue generando); keep-alive de conexiones HTTP a Groq/LiteLLM; **prewarming** de Whisper y Piper al arranque (`scripts/prewarm.sh`); VAD `stops_secs` ajustado a 0,2 (default Pipecat 1.0). Edge-TTS añade el round-trip de red, por eso Piper local gana en latencia.

---

## 7. Checklist de seguridad y backups
- [ ] **SSH solo con llaves** (`PasswordAuthentication no`), puerto no estándar opcional.
- [ ] **ufw**: permitir solo SSH y la red Tailscale; denegar el resto entrante.
- [ ] **fail2ban** para SSH.
- [ ] **Tailscale** instalado; el asistente solo accesible dentro de la tailnet (no expongas puertos a internet).
- [ ] **Acceso remoto al asistente** vía Pipecat **SmallWebRTCTransport** (P2P serverless, sin infra externa) sobre Tailscale; para NAT estricto añade STUN/TURN. SDKs cliente iOS/Android/web disponibles para hablarle desde el móvil.
- [ ] **Secretos**: `.env` fuera de git (en `.gitignore`); o cifrado con **sops-age** en `secrets/`.
- [ ] **Backups con restic** (`scripts/backup.sh` por cron diario): respaldar `data/chroma`, `data/mem0`, `config/`, `persona/`, `prompts/`, `.env`. Repositorio restic en disco externo o destino remoto cifrado.
- [ ] **Actualizaciones**: manuales y deliberadas (`docker compose pull && up -d`), **no** watchtower automático (Pipecat 1.x tiene breaking changes; controla las versiones). Fija tags de imagen.
- [ ] Healthchecks + `restart: unless-stopped` como watchdog.

---

## 8. Roadmap final actualizado por fases
- **Fase 0 — Base (sem. 1):** Ubuntu Server 24.04, particionado (NVMe=SO+Docker+modelos / SSD=datos), zram, gobernador CPU, ufw+fail2ban+SSH llaves, Tailscale, Docker+Compose.
- **Fase 1 — Voz local (sem. 2):** openWakeWord "hey jarvis" + Silero VAD + faster-whisper small int8 + Piper davefx. Validar audio headless `--device /dev/snd`. Meta: hablar y ver transcripción + respuesta hablada.
- **Fase 2 — Cerebro (sem. 3):** Pipecat 1.x: STT→LLM (Groq `llama-3.3-70b-versatile` vía LiteLLM)→TTS. Ficha de personalidad Jarvis (ingenioso, leal, humor seco) versionada en `persona/`. Fallback Cerebras/Gemini Flash.
- **Fase 3 — Memoria (sem. 4):** mem0 OSS + Chroma + embeddings HuggingFace (configura embedder explícito para que NO use OpenAI por defecto). Cron de reflexión nocturna con `prompts/reflection_nightly.md`.
- **Fase 4 — Presencia (sem. 5):** servicio `vision/`: motion OpenCV → YOLOv8n OpenVINO en iGPU → reconocimiento facial → saludo. Visión bajo demanda vía Groq Llama 4 Scout / Gemini.
- **Fase 5 — Resiliencia (sem. 6):** systemd + healthchecks, backups restic, acceso remoto WebRTC+Tailscale, prewarming y prompt caching.

**Umbrales que cambian las decisiones:** si la latencia TTS supera 300 ms → quédate en Piper (no Kokoro). Si Groq devuelve muchos 429 (free tier ~100K tokens/día) → sube a Dev Tier o desvía carga a Gemini Flash vía LiteLLM. Si la CPU de visión supera ~30% sostenido → baja `DETECT_FPS` o desactiva la presencia. Si Whisper small produce demasiados errores en español → sube a medium o large-v3-turbo int8 (sigue cabiendo en 16 GB).

---

## 9. Enlaces a recursos, repos y muestras de voz
- **Piper voices:** https://huggingface.co/rhasspy/piper-voices · **Muestras de audio:** https://rhasspy.github.io/piper-samples/
- **Piper fork mantenido (GPL):** OHF-Voice/piper1-gpl (el repo original rhasspy/piper se archivó en oct 2025)
- **HirCoir voces ES:** https://huggingface.co/HirCoir/piper-voices · Demo: tts.hircoir.eu.org
- **carlfm high (community):** https://huggingface.co/friyin/vits-piper-es_ES-carlfm-high
- **Edge-TTS:** https://github.com/rany2/edge-tts · API OpenAI-compat: https://github.com/travisvn/openai-edge-tts
- **Kokoro-82M:** https://huggingface.co/hexgrad/Kokoro-82M (voces ES: `ef_dora`, `em_alex`, `em_santa`)
- **faster-whisper:** https://github.com/SYSTRAN/faster-whisper · turbo int8: https://huggingface.co/deepdml/faster-whisper-large-v3-turbo-ct2
- **openWakeWord:** https://github.com/dscripka/openWakeWord · modelo "hey jarvis" entrenado con *"~200,000 synthetically generated clips of the 'hey jarvis' wake phrase"* + ~31.000 h de datos negativos (docs/models/hey_jarvis.md)
- **microWakeWord** (solo si vas a ESP32): https://github.com/kahrendt/microWakeWord
- **Pipecat:** https://github.com/pipecat-ai/pipecat · Migración 1.0: https://docs.pipecat.ai/pipecat/migration/migration-1.0 · SmallWebRTC: https://docs.pipecat.ai/api-reference/server/services/transport/small-webrtc
- **mem0 OSS:** https://github.com/mem0ai/mem0 · Embedders HuggingFace: https://docs.mem0.ai/components/embedders/models/huggingface
- **Wyoming (opcional HA):** rhasspy/wyoming-faster-whisper (:10300), rhasspy/wyoming-piper (:10200), o lscr.io/linuxserver/faster-whisper · piper
- **Frigate (referencia visión iGPU):** https://docs.frigate.video/frigate/hardware/ · OpenVINO UHD 630 ~15 ms
- **Coral abandono (no comprar):** https://github.com/blakeblackshear/frigate/issues/10056 · driver community: feranick/gasket-driver
- **Groq modelos:** https://console.groq.com/docs/models · `llama-3.3-70b-versatile` ($0,59/M in, $0,79/M out, 128K, 276 t/s) · Visión: `meta-llama/llama-4-scout-17b-16e-instruct` · Deprecations: https://console.groq.com/docs/deprecations (Maverick retirado 9 mar 2026)
- **Moondream (no usar local en CPU):** https://moondream.ai/

---

### Caveats finales
- Género de la voz `sharvard` no verificado en fuente primaria — escucha la muestra antes de elegirla.
- La calidad del español de Kokoro no está calificada oficialmente y es débil en frases muy cortas.
- Los modelos de visión de Groq cambian rápido (Maverick deprecado en marzo 2026; gpt-oss-120b es solo texto) — **usa Llama 4 Scout para visión y verifica el modelo vigente al implementar**.
- Edge-TTS depende de un endpoint no oficial de Microsoft y puede dejar de funcionar sin aviso; trátalo como fallback, no como dependencia crítica.
- Las cifras de latencia de motores cloud mezclan síntesis pura vs. end-to-end; la RTF ~0,2 de Piper (paper arXiv) es la mejor sustentada y la más relevante para tu objetivo local en CPU.
- Pipecat 1.x introdujo breaking changes desde 0.0.x (LLMContext universal, VAD en el user aggregator, `function_call_timeout_secs=None` por defecto): fija versiones y revisa la guía de migración.