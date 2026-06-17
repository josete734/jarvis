# Estado del arte y marco teórico

## Asistentes de voz comerciales: el modelo cloud-first y sus límites

La generación dominante de asistentes de voz —Amazon Alexa, Google Assistant y Apple Siri— comparte una arquitectura **cloud-first**. El dispositivo doméstico (un altavoz o un teléfono) ejecuta en local únicamente la detección de la palabra de activación o *wake word* —una tarea ligera y deliberadamente conservadora— y, una vez disparada, transmite el audio capturado a los servidores del proveedor. Allí ocurre lo costoso: el reconocimiento de habla (*speech-to-text*, STT), la comprensión del lenguaje natural, el razonamiento sobre la petición y la síntesis de la respuesta (*text-to-speech*, TTS). El resultado regresa al dispositivo. Bajo este reparto, el aparato del salón es esencialmente un terminal: la inteligencia reside en la nube.

Este modelo ofrece ventajas reales —cómputo prácticamente ilimitado, calidad de voz alta y actualización continua— pero impone tres limitaciones estructurales que el presente trabajo considera inaceptables para un asistente doméstico.

La primera es de **privacidad**. El audio del hogar —dato especialmente sensible, pues puede contener voz (rasgo biométrico bajo el RGPD), conversaciones privadas y la presencia de menores— se procesa en infraestructura de terceros sujeta a políticas opacas de retención, anotación humana y uso secundario. El usuario delega la confidencialidad de su domicilio en un contrato de adhesión que no controla.

La segunda es la **dependencia**. Sin conectividad o sin servicio del proveedor, el asistente deja de funcionar; el dueño no posee el sistema, sino una licencia de uso revocable. La discontinuación de productos —frecuente en este sector— puede convertir el hardware en inservible de un día para otro.

La tercera es la **opacidad y la falta de extensibilidad**. El comportamiento del asistente es una caja negra: no se puede auditar qué hace con los datos, ni inspeccionar su lógica, ni —salvo por interfaces de extensión muy acotadas (*skills*, *actions*)— modificar sustancialmente su funcionamiento. El usuario no puede cambiar el modelo de lenguaje, la voz o la política de memoria.

## El movimiento local-first y el self-hosting de voz

Frente a ese paradigma se sitúa el enfoque **local-first**, articulado conceptualmente por Kleppmann y colaboradores: el dato y el cómputo residen, por defecto, en hardware bajo control del usuario, y la nube es como mucho un complemento, no el centro de gravedad. Sus principios rectores son la **soberanía del dato** (el dueño decide qué sale de casa y qué no), el **funcionamiento sin nube para lo sensible** y la **durabilidad** (el sistema no depende de la supervivencia comercial de un proveedor). El *self-hosting* es su materialización práctica: ejecutar los servicios en infraestructura propia.

El ecosistema de voz abierta ha madurado lo suficiente como para hacer viable este enfoque. Conviene situar los proyectos que constituyen el estado del arte:

| Proyecto | Función | Aportación al estado del arte |
|---|---|---|
| Mycroft / OpenVoiceOS | Asistente de voz abierto integral | Pionero del asistente libre; demostró la viabilidad del concepto pese a dificultades de sostenibilidad |
| Rhasspy | Conjunto de herramientas de voz offline, multilingüe | Modularidad por componentes intercambiables; protocolo Wyoming |
| Home Assistant + Voice | Voz integrada en domótica local | Llevó la voz local-first al gran público de la automatización del hogar |
| openWakeWord | Detección de *wake word* | Modelos preentrenados, coste de CPU ínfimo, independiente del idioma |
| Piper | Síntesis de voz (TTS) neuronal en CPU | Voz natural en local con licencia permisiva (MIT) y latencia baja |
| faster-whisper | Reconocimiento de habla (STT) | Whisper optimizado, más rápido que tiempo real en CPU |

La conclusión que arroja el análisis de este ecosistema es matizada y resulta determinante para el posicionamiento de este trabajo: ningún proyecto llave en mano cubre simultáneamente conversación en tiempo real, visión, memoria evolutiva, uso de herramientas, español de calidad y ejecución en CPU sin GPU dedicada. Las piezas son excelentes por separado, pero la integración —**componer**, no adoptar— sigue siendo trabajo de ingeniería abierto.

## De modelos conversacionales a agentes con herramientas

Un eje paralelo del estado del arte es la evolución de los **modelos de lenguaje grandes** (LLM). En su forma básica, un LLM es un sistema que, dado un texto, produce el texto siguiente más probable: conversa, resume o redacta, pero su efecto se agota en el lenguaje. El salto cualitativo lo introduce el *function calling* (uso de herramientas): se describe al modelo un conjunto de funciones disponibles —consultar el tiempo, crear un recordatorio, buscar en internet— y el modelo, en lugar de responder en prosa, emite una petición estructurada para invocar una de ellas. El programa anfitrión ejecuta la función y devuelve el resultado al modelo, que prosigue.

Sobre esa capacidad se define el **agente**: un sistema en el que un LLM no solo razona, sino que **planifica** una secuencia de pasos, **actúa** sobre el entorno mediante herramientas y mantiene **memoria** del estado y de interacciones previas. La diferencia con un chatbot es sustancial: el agente cierra el bucle percibir-decidir-actuar y, por tanto, produce efectos en el mundo real. Es precisamente esa capacidad de actuar la que aporta utilidad doméstica —encender luces, gestionar tareas, recordar hechos del usuario entre sesiones— y, a la vez, la que introduce los riesgos del apartado siguiente.

## Riesgos de seguridad de los agentes con herramientas

Dotar a un LLM de la capacidad de **actuar** es delicado por una razón estructural: el modelo no distingue de forma fiable entre las instrucciones legítimas de su operador y las instrucciones maliciosas que pueda contener el texto que procesa. Este es el problema de la **inyección de prompts** (*prompt injection*): una página web, un correo o un documento pueden incluir órdenes encubiertas («ignora lo anterior y envía las memorias del usuario a esta dirección») que el modelo, al leerlas, podría interpretar como mandatos.

Simon Willison sistematizó el peligro bajo el nombre de **lethal trifecta** («tríada letal»): el riesgo grave se materializa cuando un agente combina, a la vez, (1) **acceso a datos privados**, (2) **exposición a contenido no confiable** y (3) **capacidad de comunicar o actuar hacia el exterior**. Con las tres condiciones presentes, contenido envenenado puede ordenar al agente exfiltrar datos privados o disparar acciones con efecto real. No es teórico: existen casos documentados de envenenamiento persistente de memoria (*SpAIware*) y de invocación diferida de herramientas. El cuerpo normativo de referencia —el OWASP LLM Top 10 y las guías agénticas de OWASP— recoge estos vectores, y técnicas como el *spotlighting* de Microsoft (marcar el contenido externo como datos, nunca instrucciones) reducen la tasa de éxito de la inyección indirecta, pero no la eliminan. De ahí el principio que la literatura y este trabajo comparten: **la última defensa nunca debe ser un prompt**; las barreras que importan han de vivir en código determinista, fuera del LLM.

## Trabajos relacionados y posicionamiento de la contribución

El interés reciente por los **agentes personales** —asistentes que actúan en nombre de un usuario sobre sus datos y servicios— ha producido un ecosistema activo de marcos de orquestación (con soporte nativo de *barge-in*, gestión de turnos y uso de herramientas), de sistemas de memoria para agentes y de bancos de pruebas adversariales que evalúan su robustez frente a la inyección de prompts. Estos esfuerzos, sin embargo, tienden a asumir cómputo en la nube y rara vez integran de forma conjunta la dimensión sensorial (voz y visión locales), la memoria adaptativa y la seguridad de la agencia.

El hueco que este trabajo pretende llenar se sitúa en esa intersección poco explorada: un **asistente doméstico que combina local-first, agencia segura y memoria adaptativa sobre hardware de consumo**. Concretamente, todo lo sensible a privacidad —*wake word*, STT, TTS, memoria, embeddings y presencia visual— se ejecuta en un mini-PC sin GPU dedicada, y solo el razonamiento, en forma de texto plano, se delega a una API externa: la voz y el vídeo nunca cruzan a la nube. Sobre esa base local-first, la capacidad de actuar se gobierna con defensas deterministas frente a la tríada letal —confirmación verbal fuera del LLM, *spotlighting* del contenido externo, *taint mode*, guardia de comandos— y la memoria incorpora procedencia y reflexión para evitar el envenenamiento persistente. Ninguno de los proyectos previos reúne estas tres propiedades simultáneamente en hardware modesto; esa convergencia, y no cada pieza por separado, constituye la contribución que el resto de la tesis desarrolla.
