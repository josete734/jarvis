# El razonamiento: el modelo de lenguaje como cerebro

Si el pipeline de voz son los oídos y la boca del asistente, el modelo de lenguaje (LLM) es su cerebro: la pieza que interpreta lo que el usuario dice, decide qué hacer y redacta lo que se va a responder. Este capítulo describe cómo se integra ese cerebro en la arquitectura, cómo se le aísla del resto del sistema para poder sustituirlo sin reescribir nada, y cómo se le dota de herramientas, contexto y personalidad.

## El único componente en la nube

El sistema es, por principio de diseño, autoalojado: el reconocimiento de voz, la síntesis, la memoria, las acciones y la búsqueda corren en hardware propio. El razonamiento es la **única excepción**, la única pieza externalizada a la nube. El motivo es de cómputo: ejecutar localmente un modelo de la capacidad necesaria exigiría una inversión en GPU desproporcionada para un homelab mono-usuario, mientras que la inferencia en proveedores remotos es barata, rápida y siempre actualizada.

Esta concesión se acota con una regla estricta: **solo viaja texto**. Al cerebro remoto nunca se le envía audio, ni imágenes sin filtrar, ni el contenido de la memoria sin control; se le manda la transcripción ya producida en local y se recibe texto que la síntesis convierte de nuevo en voz dentro de casa. El audio, que es el dato más sensible, no abandona el perímetro.

## La pasarela: LiteLLM como capa de abstracción

Acoplar el orquestador directamente a la API de un proveedor concreto sería una trampa: cada proveedor tiene su SDK, sus parámetros y sus límites, y migrar significaría tocar código. Para evitarlo, el sistema interpone **LiteLLM**, un proxy local compatible con la especificación OpenAI. El orquestador habla siempre con la misma dirección interna y es un fichero de configuración quien decide a qué modelo real se enruta cada petición.

El valor de esta capa es triple:

- **Interfaz única.** El orquestador emite peticiones en un solo formato; la heterogeneidad de los proveedores queda absorbida por la pasarela.
- **Alias.** El orquestador no pide un modelo concreto, sino un alias funcional como `jarvis-main` (cerebro principal), `jarvis-memory` (extracción barata de hechos) o `jarvis-vision`. Cambiar el modelo detrás de un alias es editar una línea de configuración, no código.
- **Fallbacks.** Si el destino principal falla, LiteLLM reintenta y cae automáticamente al siguiente alias de la cadena de respaldo, sin que el orquestador se entere.

### La saga de proveedores y la lección de diseño

Esta abstracción no es teórica: el proyecto la ha ejercitado. El cerebro principal nació siendo **Groq** (inferencia sobre hardware LPU, con un modelo de 70B y un tiempo hasta el primer token de 200–600 ms). El problema apareció con el uso continuado: las pruebas agotaban el **cupo diario gratuito** del modelo, y a media jornada el servicio degradaba a uno más pobre. La solución fue mover el cerebro a **GLM-5 servido vía OpenCode Go**, cubierto por la suscripción del usuario y sin cupo que se agote. Groq quedó relegado a *fallback* de último recurso.

Lo relevante es que ese cambio de proveedor no tocó una sola línea del orquestador: fue una reasignación del destino del alias `jarvis-main`. Esa es la lección de diseño central: **no acoplarse a un proveedor**. La capa de abstracción convirtió una migración que habría sido invasiva en un cambio de configuración.

### El truco del razonamiento desactivado

La migración trajo consigo un detalle no obvio. GLM-5, con su modo de «razonamiento» (*reasoning*) activado, devolvía respuestas **vacías**: el modelo consumía su esfuerzo en una cadena de pensamiento interna y la respuesta visible llegaba truncada o nula, lo que en un asistente de voz se traduce en silencio. La cura fue desactivarlo explícitamente, pasando un parámetro `reasoning_effort: none` a través de la pasarela. El efecto secundario es positivo: sin el sobrecoste del razonamiento, la respuesta se genera en torno a 1,5 s, dentro del presupuesto de latencia por turno. Es un recordatorio de que un modelo «más listo» no siempre encaja en un caso de uso conversacional con restricción de tiempo.

## Uso de herramientas: function calling

Un cerebro que solo conversa es un chatbot. Para actuar, el LLM dispone de **function calling**: junto a la transcripción del usuario recibe un catálogo de herramientas declaradas (nombre, descripción y parámetros), y decide por su cuenta cuándo invocar una y con qué argumentos. La respuesta del modelo deja entonces de ser texto para el usuario y pasa a ser una *tool call* que el orquestador ejecuta.

La pieza arquitectónica clave es que el **registro de herramientas está desacoplado** y es compartido por los dos canales del asistente, voz y texto. Una única fuente de verdad —un fichero de catálogo más un conjunto de implementaciones— alimenta tanto el registro sobre el servicio LLM de voz como el registro plano que consume el canal de texto de Telegram. El canal de texto no duplica reglas: reutiliza las mismas herramientas, la misma semántica de seguridad y el mismo filtrado de argumentos. Esto importa porque los LLM **alucinan argumentos** con frecuencia (por ejemplo, invocar una herramienta de agenda con un parámetro inexistente); el orquestador filtra cada llamada al esquema declarado para que una invención del modelo no haga reventar la herramienta.

Las herramientas se dividen en dos categorías:

| Categoría | Comportamiento | Ejemplos |
| --- | --- | --- |
| Solo lectura/búsqueda | Se ejecutan directamente | consultar agenda, buscar en la web, briefing |
| Acción con efecto | Nunca se ejecutan en la primera llamada: pasan por confirmación | crear recordatorio, encargar |

El detalle de la cadena de confirmación —que vive deliberadamente fuera del LLM— corresponde al capítulo de agencia; aquí basta señalar que el modelo *propone* la acción pero no es quien la *autoriza*.

## Gestión del contexto

El cerebro no recibe la frase del usuario a secas, sino un **system prompt compuesto por capas**: las reglas de comportamiento, la persona del mayordomo, el perfil del usuario, la relación y un bloque de hechos aprendidos. Estos últimos se inyectan delimitados y marcados explícitamente como datos, no como instrucciones, de modo que un hecho que pareciera contener una orden no pueda alterar el comportamiento del asistente.

El prompt se compone además **por canal**. El núcleo es común a voz y texto, pero el canal de Telegram añade un bloque que **levanta la brevedad extrema de la voz**: por escrito el asistente puede extenderse, estructurar con listas, usar negrita y compartir enlaces, cosas todas inútiles o imposibles dichas en voz alta.

Dos mecanismos más completan la gestión del contexto:

- **Inyección de la fecha y hora reales.** En cada turno se refresca en el prompt un bloque con la fecha y hora del sistema. Corrige un fallo previo: como el modelo nunca recibía la hora, **se la inventaba**.
- **El clasificador de errores del LLM.** En lugar de envolver toda falla en un manejador genérico, un módulo examina la respuesta y decide una acción concreta: ante un *rate limit*, **reintentar**; ante un contexto desbordado, **comprimir** el historial y seguir; ante un fallo de política o de credenciales, **rendirse** con un mensaje específico. Cada caso devuelve además una frase en registro de mayordomo para que el usuario nunca oiga jerga técnica.

## Delegación de lo difícil

El cerebro principal es deliberadamente **barato y rápido**, optimizado para orquestar una conversación en tiempo real, no para investigaciones largas. Cuando una petición excede su alcance, el sistema aplica un patrón de delegación: el cerebro económico **encarga el trabajo pesado a un agente más capaz**, una instancia de Claude Code que corre en el host, mediante herramientas como `investigar` (investigación de solo lectura y web) o `encargar` (acciones reales sobre el servidor). El cerebro decide *cuándo* delegar; el agente capaz ejecuta. La mecánica de esa delegación y su seguridad pertenecen al capítulo de agencia.

## Personalidad y registro

Por último, el cerebro tiene carácter. El system prompt define una **persona de mayordomo**: cortés, con el trato de «señor», al servicio del usuario. Sobre esa persona pesa, en el canal de voz, una restricción dura de **brevedad**: una respuesta hablada larga es tediosa y rompe la sensación de conversación, de modo que el prompt obliga a contestar corto. Es el mismo cerebro, la misma memoria y las mismas herramientas en voz y en texto; lo que cambia es el registro, y ese ajuste se logra —de nuevo— componiendo el prompt, no cambiando el modelo.
