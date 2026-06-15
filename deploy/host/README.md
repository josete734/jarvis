# Configuración del host (fuera de Docker)

Audio del **Anker PowerConf** (USB, mic+altavoz, AEC por hardware). Estos ficheros
fijan los niveles correctos al (re)conectar el Anker — son críticos para el wake word.

## Instalación
```
sudo cp anker-volume.service /etc/systemd/system/
sudo cp 99-anker-volume.rules /etc/udev/rules.d/
sudo systemctl daemon-reload
sudo udevadm control --reload
```

## Por qué estos valores
- **Mic 40%**: el AGC del Anker satura la voz fuerte (~amp 29487 = clipping) y eso
  hunde el score de openWakeWord a ~0. A 40% no hay clipping. Subir la ganancia es
  contraproducente.
- **PCM 80%**: salida audible (arranca al 16%, casi inaudible).
- La regla udev (291a:3301) lanza el service al conectar el Anker, así sobreviven a
  reconexiones y cambios de puerto USB (la tarjeta se llama siempre "PowerConf").

## Wake word
Palabra = **"hey Mycroft"** (`hey_mycroft_v0.1.onnx`, umbral 0.5). El modelo
`hey_jarvis` puntuaba ~0.46 con esta voz/micro; mycroft clava 0.99. El asistente
sigue llamándose Jarvis; solo cambia el disparador.
