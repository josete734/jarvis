# Resumen {.unnumbered}

Los asistentes de voz de consumo más extendidos —Alexa, Google Assistant, Siri— se sustentan en una arquitectura *cloud-first* en la que el audio del hogar y los datos del usuario se procesan en servidores de terceros. Este modelo, cómodo y potente, impone tres costes estructurales: la cesión de la privacidad del domicilio, la dependencia de un servicio externo revocable y la opacidad de un sistema que no puede auditarse ni modificarse.

Este trabajo aborda la pregunta de si es posible construir un asistente de voz personal que invierta ese modelo —que sea *local-first*, privado y extensible— sin renunciar a las capacidades modernas de un agente conversacional, y haciéndolo sobre **hardware de consumo asequible y sin GPU dedicada**. Para responderla se diseña, implementa y evalúa un sistema completo, denominado J.A.R.V.I.S., sobre un mini-PC de bajo consumo (Lenovo ThinkCentre M70q).

La solución adopta una arquitectura híbrida en la que todo lo sensible a la privacidad y a la latencia —detección de la palabra de activación, reconocimiento y síntesis de voz, memoria, visión y búsqueda— se ejecuta en local, y únicamente el razonamiento lingüístico, en forma de texto plano, se delega a un modelo de lenguaje en la nube. Sobre esa base se desarrollan tres contribuciones que, combinadas, definen la aportación del trabajo: (i) una **memoria adaptativa** que aprende hechos del usuario y los prioriza u olvida según su uso real (*recall* y *decay*); (ii) un modelo de **agencia segura** que permite al asistente ejecutar acciones reales sobre el servidor protegido por una defensa en profundidad de tres capas, bajo el principio de que *la última defensa nunca debe ser un prompt*; y (iii) una **proactividad y multicanalidad** gobernadas por presencia, que eligen cuándo y por qué canal —voz o mensajería— comunicarse.

La evaluación muestra que el sistema cumple sus objetivos de recursos y coste con holgura, alcanza latencias adecuadas en las etapas locales y queda condicionado, en la latencia total, por la pasarela remota del modelo de lenguaje. La fiabilidad se respalda con una batería de 68 pruebas automáticas y con la verificación funcional en vivo de cada subsistema. Se concluye que un asistente doméstico soberano, capaz y seguro es viable sobre hardware modesto, y se identifican las líneas de trabajo futuro.

**Palabras clave:** asistente de voz, *local-first*, privacidad, agentes de lenguaje, seguridad de IA, inyección de prompts, memoria adaptativa, computación en el borde.

\bigskip

## Abstract {.unnumbered}

Mainstream consumer voice assistants —Alexa, Google Assistant, Siri— rely on a cloud-first architecture in which household audio and user data are processed on third-party servers. This convenient and powerful model carries three structural costs: surrendering the privacy of the home, depending on a revocable external service, and the opacity of a system that cannot be audited or modified.

This work investigates whether it is possible to build a personal voice assistant that inverts that model —one that is local-first, private and extensible— without giving up the modern capabilities of a conversational agent, and doing so on **affordable consumer hardware without a dedicated GPU**. To answer it, a complete system named J.A.R.V.I.S. is designed, implemented and evaluated on a low-power mini-PC (Lenovo ThinkCentre M70q).

The solution adopts a hybrid architecture in which everything privacy- and latency-sensitive —wake-word detection, speech recognition and synthesis, memory, vision and search— runs locally, and only the linguistic reasoning, as plain text, is delegated to a cloud language model. On that foundation, three contributions are developed: (i) an **adaptive memory** that learns facts about the user and prioritises or forgets them based on actual use (recall and decay); (ii) a **safe agency** model letting the assistant perform real actions on the server, protected by a three-layer defence-in-depth under the principle that *the last line of defence must never be a prompt*; and (iii) presence-governed **proactivity and multichannel** behaviour that decides when and through which channel —voice or messaging— to communicate. The evaluation shows that a sovereign, capable and secure home assistant is feasible on modest hardware.

**Keywords:** voice assistant, local-first, privacy, language agents, AI security, prompt injection, adaptive memory, edge computing.
