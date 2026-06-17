# Conclusiones y trabajo futuro

## Conclusiones

Esta tesis partía de una pregunta concreta: si es posible construir un asistente de voz personal **capaz** como un agente moderno y **soberano** como un sistema *local-first*, sobre hardware de consumo y sin GPU dedicada. El sistema diseñado, implementado y evaluado a lo largo del documento permite responder afirmativamente, con los matices que la propia evaluación impone.

El trabajo demuestra, en primer lugar, que la **arquitectura híbrida** es la clave de la viabilidad: al mantener en local todo lo sensible —voz, visión, memoria, búsqueda— y delegar a la nube únicamente el razonamiento en forma de texto, un mini-PC de 35 W sostiene un pipeline conversacional completo. El audio del hogar y el rostro del usuario nunca abandonan la máquina; solo cruza la frontera el texto imprescindible para pensar. La privacidad deja de ser una promesa contractual para convertirse en una propiedad arquitectónica.

En segundo lugar, las tres contribuciones planteadas se materializaron y verificaron:

- La **memoria adaptativa** con *recall* y *decay* resuelve la tensión entre recordar y saturar: el asistente prioriza lo que el usuario usa y archiva —sin borrar— lo que cae en desuso, manteniendo el contexto dentro de un presupuesto y sin la maquinaria de un *vector store*.
- El modelo de **agencia segura en tres capas** permite que el asistente actúe sobre el servidor sin convertirse en un peligro, separando con nitidez dónde aporta valor la inteligencia del modelo (juzgar el riesgo) y dónde debe mandar el código determinista (garantizar la confirmación y bloquear lo letal). El principio *la última defensa nunca debe ser un prompt* se reveló no como un eslogan, sino como una guía de diseño con consecuencias concretas.
- La **proactividad y multicanalidad** gobernadas por presencia dotan al sistema de criterio sobre cuándo hablar y por qué canal, transformando un conjunto de capacidades en un comportamiento de mayordomo coherente.

La evaluación es honesta sobre los límites de lo logrado: el sistema cumple con holgura sus objetivos de recursos y coste, y alcanza buenas latencias en las etapas locales, pero la latencia total queda condicionada por la pasarela remota del modelo de lenguaje, cuyo comportamiento no se ha caracterizado de forma estadística. La fiabilidad se sostiene sobre una batería de pruebas y la verificación en vivo de cada subsistema, a falta de una campaña de medición cuantitativa a gran escala. Es, en suma, una demostración sólida de viabilidad, no un estudio estadístico de rendimiento.

Más allá del artefacto, el proyecto deja una lección transferible sobre la **ingeniería de agentes seguros**: la combinación de inteligencia probabilística para el criterio y de barreras deterministas para los límites —defensa en profundidad— es un patrón aplicable a cualquier sistema en el que un modelo de lenguaje pueda actuar sobre el mundo real.

## Trabajo futuro

El sistema admite varias líneas de continuación, ordenadas por madurez:

- **Completar el subsistema de visión.** El código de presencia y reconocimiento está construido y a la espera únicamente de la cámara física; su activación cerrará la integración voz-visión y permitirá medir su rendimiento real.
- **Caracterización cuantitativa.** Una campaña de medición con percentiles de latencia, tasa de error de reconocimiento por hablante y consumo eléctrico real con vatímetro convertiría la demostración de viabilidad en una evaluación estadística.
- **Voz desde otra estancia.** La arquitectura admite clientes de red (satélites de bajo coste como ESP32 o un cliente móvil) que extiendan el asistente más allá del alcance del micrófono del servidor.
- **Refuerzos de seguridad.** Identificación de hablante como verja adicional para acciones sensibles, validación criptográfica completa de la identidad en el panel y suites adversariales de inyección de prompts.
- **Memoria semántica.** Si el volumen de hechos creciera, podría incorporarse recuperación por similitud como complemento —no sustituto— de la búsqueda léxica actual.

En conjunto, el trabajo no agota el problema, pero sí establece que un asistente doméstico privado, capaz y seguro es alcanzable hoy, con software libre y hardware modesto, y ofrece un diseño concreto y verificado sobre el que seguir construyendo.
