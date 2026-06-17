# Introducción

## Contexto y motivación

En poco más de una década, los asistentes de voz han pasado de ser una curiosidad de laboratorio a un electrodoméstico cotidiano: decenas de millones de hogares conviven con un altavoz que escucha, responde y, cada vez más, actúa. Sin embargo, la comodidad de estos sistemas se ha construido sobre una premisa que rara vez se discute: el micrófono del salón es, en realidad, un terminal que envía cuanto oye —tras la palabra de activación— a la infraestructura de una gran corporación, donde se transcribe, se interpreta y, a menudo, se almacena y se anota. El usuario obtiene un servicio excelente a cambio de ceder la confidencialidad de su domicilio y de aceptar una dependencia total de un proveedor que puede cambiar las reglas, subir el precio o, sencillamente, discontinuar el producto.

Paralelamente, la irrupción de los **modelos de lenguaje grandes** (LLM) ha transformado lo que cabe esperar de un asistente. Ya no se trata solo de reconocer comandos fijos, sino de mantener una conversación natural, razonar sobre peticiones ambiguas y —mediante el uso de herramientas— **actuar** en el mundo: consultar una agenda, gestionar un servidor, recordar lo que se dijo la semana pasada. Esta nueva capacidad de agencia multiplica la utilidad del asistente y, a la vez, introduce una superficie de riesgo inédita, porque un sistema que puede actuar es un sistema que puede ser engañado para actuar mal.

Estas dos corrientes —la preocupación creciente por la privacidad y la soberanía digital, y la madurez de los modelos de lenguaje— convergen en una pregunta que vertebra esta tesis.

## Planteamiento del problema y objetivos

**¿Es posible construir un asistente de voz personal que sea, a la vez, capaz como un agente moderno y soberano como un sistema *local-first*, ejecutándose sobre hardware de consumo asequible y sin recurrir a una GPU dedicada?**

Responder a esta pregunta exige resolver varias tensiones de diseño que no son triviales: la potencia de un LLM moderno frente a las limitaciones de un mini-PC; la utilidad de la agencia frente a su peligrosidad; la conveniencia de una memoria persistente frente a la degradación que provoca saturar el contexto del modelo; y la ambición de un asistente proactivo frente al riesgo de convertirlo en un intruso molesto.

El objetivo general se concreta en los siguientes objetivos específicos:

1. **Diseñar una arquitectura híbrida** que mantenga en local todo lo sensible a privacidad y latencia (voz, visión, memoria, búsqueda) y delegue a la nube únicamente el razonamiento, en forma de texto.
2. **Implementar un pipeline de voz** completo y de baja latencia (palabra de activación, reconocimiento, síntesis) sobre una CPU sin aceleración gráfica.
3. **Dotar al asistente de una memoria adaptativa** que aprenda de la conversación y gestione el olvido de forma que priorice lo relevante sin saturar el contexto.
4. **Habilitar la agencia segura**: que el asistente pueda ejecutar acciones reales con un modelo de seguridad robusto frente al error y la manipulación.
5. **Construir proactividad y multicanalidad** gobernadas por la presencia del usuario.
6. **Evaluar** el sistema resultante en términos de latencia, recursos, coste y fiabilidad.

## Contribuciones

El trabajo realiza tres contribuciones principales, que el documento desarrolla en profundidad:

- **Una memoria adaptativa con *recall* y *decay*.** En lugar de almacenar todo o de recurrir a la maquinaria de un *vector store*, se propone un almacén de hechos con metadatos de uso que prioriza lo que el usuario menciona y archiva —sin borrar— lo que cae en desuso, manteniendo el contexto inyectado dentro de un presupuesto.
- **Un modelo de agencia segura en tres capas.** Para permitir que el asistente actúe sobre el sistema sin convertirlo en un peligro, se articula una defensa en profundidad que combina confirmación determinista, juicio de riesgo asistido por el modelo y un guardia de comandos infalsificable, bajo el principio rector de que *la última defensa nunca debe ser un prompt*.
- **Un enrutado de la comunicación por presencia.** El asistente decide cuándo hablar (silencio por defecto, filtrado por una puerta única) y por qué canal (voz si el usuario está en casa, mensajería si está fuera), integrando voz, texto y visión en una sola política coherente.

## Estructura del documento

El resto de la tesis se organiza como sigue. El **Capítulo 2** revisa el estado del arte y el marco teórico. El **Capítulo 3** expone la metodología y los materiales. El **Capítulo 4** describe la arquitectura general del sistema. Los **Capítulos 5 a 11** detallan los subsistemas: el pipeline de voz, el razonamiento, la memoria, la proactividad y multicanalidad, la agencia, la visión y, transversalmente, la seguridad y la privacidad. El **Capítulo 12** presenta la evaluación. El **Capítulo 13** recoge las conclusiones y las líneas de trabajo futuro. Cierran el documento las referencias y los anexos.
