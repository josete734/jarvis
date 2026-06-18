# Jarvis Glasses

App Android (Kotlin + Jetpack Compose) que convierte unas gafas Bluetooth en un
asistente de voz manos libres para el servidor **Jarvis**.

Un *Foreground Service* escucha **"Hey Mycroft"** en continuo y on-device
(wake word con [openWakeWord](https://github.com/dscripka/openWakeWord) sobre
ONNX Runtime) captando el micro de las gafas (perfil BLE Audio / SCO). Al
detectar la palabra de activacion graba la orden, la envia al servidor
(`POST {base}/voice`) y reproduce por las gafas el WAV de respuesta.

```
[Gafas BT] --mic--> [WakeWord ONNX] --"Hey Mycroft"--> [graba + VAD]
        --WAV 16k--> POST {base}/voice --WAV--> [reproduce por las gafas]
```

## Que hace

- Wake word totalmente local (melspectrogram -> embedding -> hey_mycroft, ONNX).
- Endpointing por VAD (silero_vad.onnx): corta tras ~800 ms de silencio o 10 s.
- Audio de voz 16 kHz mono PCM16, ruteado a las gafas via
  `AudioManager.setCommunicationDevice()`.
- Servicio en primer plano (`microphone`) con notificacion persistente y
  `START_STICKY` (se relanza si el sistema lo mata).

## Requisitos

- Android 9+ (minSdk 28; recomendable 12+/API 31 para BLE Audio).
- Gafas emparejadas y funcionando como auricular (p. ej. Ray-Ban Meta con la
  app **Meta AI**; las gafas deben aparecer como dispositivo de comunicacion
  BLE/SCO en el sistema).
- Conectividad al servidor Jarvis por **LAN** o **Tailscale** (tailnet).
- Servidor Jarvis con el endpoint `/voice` y el secreto `EVENTS_SECRET`.

## Construir el APK

Con Android Studio: abre el modulo y *Run* / *Build > Build APK(s)*.

Por linea de comandos:

```bash
cd /opt/jarvis/clients/android/JarvisGlasses
./gradlew assembleDebug
# APK en app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Detalles del modulo: `com.jarvis.glasses`, compileSdk 35, minSdk 28,
targetSdk 35, Kotlin 2.0.21, AGP 8.7.3, JDK 17.

## Configurar

En la pantalla principal:

1. **URL del servidor**: la base sin `/voice`, por ejemplo
   `https://host.tailnet.ts.net` o `http://192.168.0.32:8070`.
2. **Secreto**: el valor de `EVENTS_SECRET` del servidor (se envia en la
   cabecera `X-Jarvis-Events-Secret`).
3. Pulsa **Guardar configuracion** (se persiste en DataStore).

## Usar

1. Pulsa **Iniciar**. Acepta los permisos: micro (`RECORD_AUDIO`),
   notificaciones (`POST_NOTIFICATIONS`), Bluetooth (`BLUETOOTH_CONNECT`) y la
   exencion de optimizacion de bateria.
2. Comprueba en la tarjeta de estado que el micro entra por las gafas
   ("Micro: gafas (BLE/SCO)").
3. Puedes **bloquear la pantalla**: el servicio sigue en primer plano.
4. Di **"Hey Mycroft" + tu orden en una sola frase continua**. El estado
   pasara `LISTENING -> RECORDING -> THINKING -> SPEAKING` y oiras la respuesta
   por las gafas.
5. **Parar** detiene el servicio y libera el micro.

## Caveats honestos

- **Bateria**: escuchar el micro en continuo consume. La exencion de
  optimizacion de bateria es necesaria para que no lo congelen en segundo plano.
- **Calidad SCO**: en perfil SCO el micro suele ser **mono 8-16 kHz**; el wake
  word y el ASR funcionan, pero no esperes audio de alta fidelidad.
- **Re-armar tras reinicio**: la app no arranca sola al reiniciar el telefono;
  hay que abrirla y pulsar Iniciar otra vez.
- **Nothing OS / fabricantes agresivos**: desactiva manualmente la optimizacion
  de bateria y permite el *autostart* de la app, o el sistema matara el
  servicio. Lo mismo aplica a MIUI, OneUI, etc.
- **Enrutado del micro**: si las gafas no estan conectadas/activas como
  dispositivo de comunicacion, el micro caera al del telefono y el estado
  mostrara "no enrutado a las gafas".
- **Red**: con Tailscale, manten la VPN activa; con LAN, el telefono debe estar
  en la misma red que el servidor.
