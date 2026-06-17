# Fase C — Encender la visión (cuando llegue la cámara USB)

Todo está construido y verificado salvo lo físico. Modelos presentes
(`/var/lib/jarvis/models/yolo11n_int8_320_openvino` + `insightface/buffalo_sc`),
código de presencia continua + latido listo (`services/vision/presence.py`), y el
routing por presencia (Fase B) ya enruta voz/Telegram. Pasos al conectar la webcam:

## 0. Hardware
Recomendada **Logitech C920/C922** (FOV 78°, UVC plug&play). Enchufar al USB.

## 1. Verificar que el sistema ve la cámara
```bash
ls -l /dev/video0                 # debe existir
v4l2-ctl --list-devices           # (opcional) confirma el modelo
```
Si `/dev/video0` no aparece, probar otro puerto USB / `dmesg | grep -i uvc`.

## 2. Enrolar la cara de José (una vez, hay que estar delante)
El servicio de visión es de un solo consumidor de la cámara → parar primero:
```bash
cd /opt/jarvis
sudo docker compose stop vision
sudo docker compose run --rm vision python3 enroll_face.py --name jose --from-camera 8
# (toma ~8 muestras; mira a la cámara, buena luz). Crea /srv/jarvis/faces/jose.npy
ls -l /srv/jarvis/faces/jose.npy
```

## 3. Encender la presencia
Poner `DISABLE_PRESENCE=false` en el servicio `vision` del `docker-compose.yml`
(hoy está `true`), y levantar:
```bash
sudo docker compose up -d vision
sudo docker compose logs -f vision      # ver "person detected" / "presence post"
```

## 4. Verificar el routing (Fase B, ya implementado)
- **Te ve** → `is_present()` True → los avisos van por **VOZ**.
- **No te ve** (pero la cámara late) → tras ~90s **ausente** → avisos por **Telegram**.
- **Sin cámara / vision caído** → fail-safe **presente** (como hoy).
- Al volver a aparecer tras ≥90s ausente → **saludo** por voz (cooldown 30 min, lo decide
  el orquestador en `events.py`, según la hora: buenos días/tardes/noches).

Comprobar el estado en vivo:
```bash
# el orquestador recibe /event/presence (person + beat); mirar sus logs
sudo docker compose logs --since 2m orchestrator | grep -i presence
```

## Parámetros para afinar (env del servicio vision)
| Var | Default | Qué |
|-----|---------|-----|
| `DETECT_FPS` | 2 | fotogramas/s (presencia no necesita más) |
| `PERSON_CONF` | 0.35 | umbral YOLO 'person' (sube si hay falsos positivos) |
| `PRESENCE_POST_SECS` | 8 | throttle de "te veo" al orquestador |
| `VISION_BEAT_SECS` | 30 | latido 'vision viva' |
| `MATCH_THRESHOLD` | 0.45 | similitud de cara (en `presence.py`) |
| `PRESENCE_TTL` (orquestador) | 45 | visto hace <45s = presente |
| `PRESENCE_REMOTE_WINDOW` | 900 | tras Telegram, remoto 15 min |

## Notas
- Las webcams USB **no ven en oscuridad** (sin IR): de noche sin luz, no hay detección
  → el sistema lo trata como ausente (avisa por Telegram). Esperado.
- Fase D (opcional, después): interacción por cámara — "¿necesita algo?" si te acercas
  tras un rato en silencio, saludo con gesto (YOLO-pose). No imprescindible.
