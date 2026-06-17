# Percepción y expresión: el pipeline de voz

## Visión general: una cadena conversacional en tiempo real

El subsistema de voz constituye la frontera sensorial del asistente: el lugar donde el sonido se convierte en intención y la intención vuelve a convertirse en sonido. Su objetivo de diseño es exigente y doble. Por un lado, debe completar un turno conversacional —de la palabra del usuario a la respuesta hablada— en torno a 1,3 a 2,0 segundos. Por otro, debe respetar un principio de privacidad estricto: el audio nunca abandona el equipo doméstico. Solo el texto necesario para razonar viaja a la nube; la captura, la transcripción y la síntesis ocurren íntegramente en local, sobre un mini-PC sin GPU.

La orquestación de esa cadena recae en Pipecat, un marco de voz en tiempo real cuyo modelo de ejecución es un **pipeline de frames**. Cada fragmento de audio, cada transcripción parcial y cada señal de control circula como un *frame* a través de una secuencia ordenada de procesadores, de modo que la latencia se solapa: el sistema puede empezar a sintetizar la primera frase de la respuesta mientras el modelo de lenguaje todavía genera el resto.

```mermaid
flowchart LR
    mic["Captura USB (AEC hardware)"] --> gate["WakeWordGate + openWakeWord"]
    gate --> stt["faster-whisper small INT8"]
    stt --> agg["Agregador + Silero VAD + smart-turn"]
    agg --> llm["LLM en la nube (solo texto)"]
    llm --> tts["Piper TTS davefx"]
    tts --> out["Reproducción USB"]
```

Un detalle de integración resulta crítico: la detección de actividad de voz (VAD) se sitúa en el agregador de usuario, no en el transporte de entrada. Colocarla en el transporte, como hace la configuración heredada, ejecutaría el VAD *antes* del filtro de palabra de activación y desmontaría el diseño de privacidad que se describe a continuación.

## La palabra de activación: despertar sin escuchar siempre

El primer eslabón es un *gate* (compuerta) de palabra de activación. La motivación es de privacidad: sin un disparador local, la única alternativa sería transcribir el audio de forma permanente y buscar la palabra clave en el texto, lo que implica que un micrófono abierto envíe sonido al reconocedor 24 horas al día. Eso es, además, inviable en esta CPU. El *gate* invierte la lógica: mientras el asistente «duerme», descarta todo el audio entrante y no transcribe nada; solo cuando detecta la palabra de activación abre el resto del pipeline. Nada se transcribe hasta que el sistema despierta.

La detección corre a cargo de openWakeWord, un detector ligero basado en modelos ONNX preentrenados que consume entre el 1 y el 3 % de un núcleo. El audio llega a 16 kHz en mono y se evalúa en bloques de 1280 muestras (80 ms); cuando la puntuación supera el umbral de 0,5, el sistema despierta, reinicia el modelo y abre una ventana de escucha de unos 45 segundos que se renueva mientras el usuario siga hablando.

La elección de la palabra concreta fue empírica. El modelo natural, «hey jarvis», resultó poco fiable con el micrófono empleado: disparaba de forma irregular. El modelo «hey Mycroft», en cambio, detectaba con solidez sobre el mismo hardware. La decisión, por tanto, fue desacoplar el disparador del nombre: el asistente sigue llamándose Jarvis, pero la palabra que lo despierta es «hey Mycroft». Es un *trade-off* deliberado —una pequeña incoherencia de marca a cambio de fiabilidad de detección— justificado por la medición, no por la preferencia.

## VAD y fin de turno: saber cuándo ha terminado el usuario

Detectar el comienzo del habla es sencillo; detectar su final no lo es. Una pausa para pensar no debe interpretarse como cesión del turno, o el asistente interrumpirá al usuario a media frase. El sistema combina dos mecanismos. El VAD de Silero distingue voz de silencio en tiempo real. Sobre él opera *smart-turn*, un pequeño modelo ONNX (con soporte de español) que analiza si la frase está semánticamente completa. La estrategia es eficiente: una pausa de unos 200 ms dispara el análisis semántico (de 12 a 95 ms en CPU), que decide si el turno ha terminado de verdad. Así se resuelve de raíz el problema clásico de que el asistente corte al usuario cuando este simplemente duda.

## STT: reconocimiento adaptado al español en CPU

La transcripción emplea faster-whisper en su variante `small` con cuantización INT8, que ocupa alrededor de 1 GB de RAM y opera más rápido que el tiempo real en este equipo. La elección refleja varios *trade-offs*. El modelo `medium` ofrecería mayor precisión, pero su coste lo hace inviable sin GPU. Una alternativa especializada como parakeet, considerada en la planificación, se descartó por una razón insalvable: solo soporta inglés, lo que lo inhabilita para un asistente en español. El modelo `small` quedó así como decisión definitiva, validada con transcripción de español «casi perfecta». El diseño conserva su flexibilidad: como Pipecat acepta cualquier backend compatible con la interfaz de OpenAI, sustituir el reconocedor en el futuro sería cuestión de configuración, sin cambios de código.

## TTS: síntesis local y rápida

La síntesis de voz recae en Piper con la voz `es_ES-davefx-medium` (masculina, 22,05 kHz, licencia MIT), embebida en el orquestador sin contenedor aparte. Es local, ligera y suficientemente rápida: en la validación produjo voz en español en 1,8 segundos, y en régimen de *streaming* sintetiza la primera frase mientras el modelo de lenguaje sigue generando, lo que recorta la latencia percibida.

| Etapa | Tecnología | Métrica de referencia |
| --- | --- | --- |
| Wake word | openWakeWord `hey_mycroft` | score 0,99 (clip sintético) |
| Fin de turno | Silero VAD + smart-turn | ~200 ms pausa + 12–95 ms análisis |
| STT | faster-whisper `small` INT8 | español casi perfecto |
| LLM | Modelo en la nube (solo texto) | TTFB ~0,49 s (Groq) |
| TTS | Piper `es_ES-davefx-medium` | voz en 1,8 s |

## Caso de estudio: el detector que puntuaba 0,000

La primera avería seria del proyecto ilustra un método de depuración sistemática que merece exponerse por sí mismo. El síntoma era desconcertante: con alguien hablando frente al micrófono, el detector devolvía **exactamente 0,000, turno tras turno**. Un cero perfecto y sostenido es, en sí mismo, una pista: un modelo de palabra de activación expuesto a voz real produce *algo*, aunque sea un valor bajo ante una frase ajena. Un cero absoluto sugiere ausencia de señal, no fallo de clasificación.

El diagnóstico procedió por hipótesis y descartes. Primero se inyectó un clip sintético directamente al detector, sin pasar por el micrófono: dio **0,99**. Ese único experimento absolvió al modelo y al *gate*, y acotó el problema *aguas arriba*, en la captura. A continuación se bajó el umbral del VAD a 0,0 para descartar que filtrara la voz: el score seguía en cero. Finalmente se instrumentó el detector para registrar la amplitud máxima de cada bloque capturado, y la evidencia fue concluyente: una amplitud sostenida de ≈15 sobre un formato en el que la voz real supera 1000. El detector funcionaba con total honestidad: puntuaba un silencio perpetuo.

La causa raíz no estaba en el software de detección sino en la **selección del dispositivo de audio**: el sistema capturaba de un dispositivo mudo —el micrófono muerto del jack de la placa— en lugar de la entrada prevista. Dos factores lo hacían casi inevitable. Los índices de dispositivo eran inestables entre reinicios (la tarjeta pasaba de `card 1` a `card 0` según el orden de detección USB), de modo que un índice fijo apuntaba al sitio equivocado o provocaba un fallo. Además, contenedores de prueba sin detener retenían el dispositivo correcto como ocupado.

La solución elevó el incidente a principio de diseño: **identificar los dispositivos por nombre, nunca por posición.** En el código, una función recorre los dispositivos y elige por nombre; en la capa ALSA, una configuración asimétrica fija la captura y la reproducción por nombre de tarjeta, y los índices numéricos se abandonan por completo. Un nombre es una propiedad estable del hardware; un índice es un hecho circunstancial del último arranque.

El caso tuvo una segunda fase. Una vez que el micrófono capturaba señal, apareció un problema de **saturación o *clipping***: ganancia excesiva que distorsionaba la entrada y degradaba la detección. La resolución combinó dos ajustes: la adopción de la palabra «hey Mycroft», más robusta sobre este hardware, y el ajuste de la ganancia de captura a un nivel que evita el recorte. La lección metodológica es transferible: ante un detector que devuelve cero absoluto, conviene sospechar primero de la señal y solo después del modelo, y un test sintético que aísle el componente ahorra horas de mirar en el lugar equivocado.

## Eco y barge-in: que el asistente no se oiga a sí mismo

El último reto del manos libres es el eco acústico: si el micrófono capta la propia voz sintetizada del asistente por el altavoz, el sistema se interrumpe a sí mismo y se vuelve inutilizable. El marco no aporta cancelación de eco acústico (AEC), así que el síntoma documentado era precisamente esa auto-interrupción. La solución definitiva resultó ser de **hardware**: un altavoz de conferencia USB Anker PowerConf que cancela el eco en el propio dispositivo, sin coste de CPU. Esto preserva, además, la capacidad de *barge-in* —que el usuario pueda interrumpir al asistente mientras habla— porque distingue correctamente la voz humana de la reproducción propia. Como respaldo histórico quedan dos planes por software, nunca activados al bastar la solución por hardware. El criterio de aceptación fue cuantitativo: un incremento de RMS no superior a unos 6 dB sobre el silencio de referencia y locución inaudible en la captura, más una prueba de *double-talk* que valida el *barge-in*.
