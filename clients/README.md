# Clientes de Jarvis (hablar por las gafas Meta)

Apps que usan unas **gafas Meta** (Oakley/Ray-Ban, micro+altavoz Bluetooth) como entrada/salida
de voz y hablan con Jarvis a través del endpoint **`POST /voice`** del orquestador
(`services/orchestrator/events.py`): audio → Whisper → cerebro → voz **carlfm** → audio.

| Cliente | Plataforma | Modo | Estado |
|---|---|---|---|
| **`android/`** | Android (Nothing/CMF) | **Wake word "Hey Mycroft" siempre escuchando** (foreground service) | ✅ recomendado para manos libres en el bolsillo |
| `ios/` | iOS | Push-to-talk en primer plano | secundario (iOS no permite escucha continua fiable en background) |

**Por qué Android para el always-on:** iOS mata la captura de micro en segundo plano (~50 s);
Android la mantiene indefinidamente con un *foreground service* de tipo micrófono. El wake word
"Hey Mycroft" corre on-device (openWakeWord, el mismo modelo que el Anker de casa).

## Conexión al servidor
Ambos clientes llaman a `/voice` con la cabecera `X-Jarvis-Events-Secret` = `EVENTS_SECRET`.
El endpoint vive en el orquestador (puerto 8070, hoy en `127.0.0.1`). Para llegar desde el móvil:
- **En casa (LAN):** mapea el puerto a la red en `docker-compose.yml` y usa `http://<IP-host>:8070`.
- **En cualquier sitio:** `tailscale up` + `tailscale serve --bg 8070` en el host; el móvil con
  Tailscale usa `https://<host>.<tailnet>.ts.net`.

Ver el README de cada subcarpeta para construir e instalar.
