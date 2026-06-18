# JarvisGlasses — app iOS para hablar con Jarvis por las gafas Meta

App mínima (SwiftUI, push-to-talk) que usa las **Oakley/Ray-Ban Meta** como micro+altavoz
Bluetooth (perfil **HFP**) y habla con Jarvis: graba tu voz por las gafas → la manda al
endpoint `POST /voice` del orquestador → reproduce por las gafas la respuesta **con la voz
de mayordomo (Piper carlfm)**.

## Por qué funciona
El micro de las gafas Meta es un **micrófono Bluetooth HFP estándar** (confirmado en la doc
de desarrolladores de Meta: *"HFP · 8 kHz mono · Voice capture from the glasses microphone"*,
`.allowBluetoothHFP`). No hace falta el SDK de Meta para el audio: basta `AVAudioSession` +
`.allowBluetoothHFP` (es lo que hace el proyecto VisionClaw). No se puede cambiar "Hey Meta",
así que el disparo lo pone la app (push-to-talk; o el Botón de Acción vía un App Intent).

## Montar en Xcode (tienes cuenta de desarrollador)
1. Nuevo proyecto **iOS App** (SwiftUI), nombre `JarvisGlasses`. Sustituye los 3 `.swift`
   por los de esta carpeta (`JarvisGlassesApp`, `ContentView`, `VoiceClient`).
2. **Info.plist** → añade `NSMicrophoneUsageDescription` = "Para hablar con Jarvis".
3. Capabilities → **Background Modes → Audio** (opcional, para grabar con pantalla apagada).
4. Firma con tu equipo de desarrollador, conecta el iPhone y *Run*.

## Configurar
- En la app, **⚙︎ Ajustes**:
  - **URL del servidor**: `http://192.168.0.32:8070` (misma WiFi de casa) o tu URL de Tailscale.
  - **Secreto**: el valor de `EVENTS_SECRET` del `.env` de Jarvis.
- Empareja las gafas con la app **Meta AI**; comprueba en *Ajustes > Bluetooth* del iPhone que
  quedan "Conectadas para llamadas y audio".

## Exponer Jarvis al iPhone
El endpoint vive en el orquestador (`events.py`, puerto 8070). Hoy está mapeado a
`127.0.0.1:8070` (solo local). Para que el iPhone llegue:
- **Casa (LAN):** en `docker-compose.yml`, cambia el mapeo del orquestador
  `127.0.0.1:8070:8070` → `8070:8070`; el iPhone usa `http://<IP-del-host>:8070`.
- **Desde cualquier sitio:** `sudo tailscale up` en el host + `tailscale serve` para `/voice`,
  e instala Tailscale en el iPhone (misma tailnet). URL `https://<host>.<tailnet>.ts.net`.

## Uso
Mantén pulsado el botón, habla, suelta. Verás la transcripción y la respuesta, y oirás a
Jarvis por las gafas. El indicador arriba dice si el micro entró por las gafas (HFP, verde) o
por el iPhone (naranja) — si sale naranja, revisa el emparejamiento Bluetooth.

## Caveats (HFP)
- Micro en **8 kHz mono** (calidad de llamada). Suficiente para Whisper.
- Mientras el micro está activo, la salida también es mono (HFP y A2DP son excluyentes).
- Endpoints disponibles: `POST /voice` (audio↔audio) y `POST /ask` (texto↔texto, si prefieres
  STT on-device con el framework Speech de Apple). Ambos con cabecera `X-Jarvis-Events-Secret`.
