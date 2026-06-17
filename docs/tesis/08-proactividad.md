# Proactividad y multicanalidad

## El problema de la proactividad

Un asistente que solo responde cuando se le pregunta es predecible y, por ello, inofensivo: el usuario conserva siempre el control de cuándo empieza la interacción. Dar al sistema la capacidad de **iniciar la comunicación por su cuenta** —avisar de algo sin que nadie lo haya pedido— cambia esa relación de raíz. Bien hecho, es lo que separa a un mayordomo de un buscador con voz: el sistema recuerda, anticipa y avisa. Mal hecho, es la forma más rápida de destruir la confianza. Un asistente que interrumpe de más se convierte en ruido, y a un sistema ruidoso se le acaba ignorando o apagando. El coste de un falso positivo proactivo (molestar sin motivo) es asimétricamente mayor que el de un falso negativo (callar cuando quizá valía la pena hablar).

De esa asimetría nace el principio de diseño que gobierna todo el subsistema: **silencio por defecto**. El sistema no habla salvo que tenga una razón clara para hacerlo, y la carga de la prueba recae sobre el aviso, no sobre el silencio. La proactividad se trata, por tanto, no como una funcionalidad que se activa, sino como una excepción que debe justificarse y atravesar una serie de filtros antes de alcanzar al usuario.

## El heartbeat y la puerta única

El mecanismo tiene dos piezas. La primera es un **heartbeat** (latido) periódico: una señal temporizada que despierta al sistema a intervalos regulares para que se plantee si tiene algo que decir. Sin este latido, el asistente nunca tendría ocasión de tomar la iniciativa, porque su ciclo normal es puramente reactivo. El latido no decide nada por sí mismo; solo abre la oportunidad.

Quien decide es `brain_review`, un momento de reflexión en el que el propio modelo de lenguaje revisa el estado del día y se pregunta si vale la pena anticiparse a algo. Su sesgo está deliberadamente cargado hacia el **silencio**: la respuesta por defecto a «¿hay algo verdaderamente oportuno?» es *no*. Solo cuando aparece una razón suficientemente buena el sistema rompe el silencio. Delegar este juicio al LLM evita codificar reglas rígidas sobre qué es «oportuno», a cambio de aceptar la variabilidad propia de un modelo; el sesgo conservador acota esa variabilidad por el lado seguro.

Aunque `brain_review` decida hablar, ningún aviso llega directamente al usuario. Toda salida proactiva atraviesa una **puerta única**, el `ProactiveGate`, que concentra en un solo punto todas las reglas de cortesía. Tener una primitiva única de salida es una decisión arquitectónica importante: garantiza que no exista ningún camino lateral por el que un aviso pueda escapar de los filtros. La puerta aplica de golpe:

| Filtro | Qué hace |
| --- | --- |
| No molestar (DND) | Bloquea cualquier aviso mientras el modo está activo |
| Horario de silencio | Suprime interrupciones de voz en franjas nocturnas |
| Presupuesto por hora | Limita el número máximo de avisos en una ventana de tiempo |
| Deduplicación | Descarta mensajes repetidos que ya se han dicho |
| Tiers | Gradúa el derecho de cada aviso a interrumpir |

El sistema de **tiers** (niveles) merece detalle: clasifica cada aviso en `ambient`, `info` o `critical`. Un aviso `ambient` apenas tiene derecho a interrumpir y cede ante casi cualquier filtro; uno `critical` puede atravesar restricciones que detendrían a los demás. Así, el mismo mecanismo que silencia el ruido de fondo deja pasar lo que de verdad importa. La combinación de un juez conservador y una puerta con presupuesto y niveles materializa el principio de silencio por defecto sin volver el sistema inútil.

## Multicanalidad: el texto como canal de primera clase

El sistema habla por voz, pero la voz no es su único cuerpo. Se añadió un **canal de Telegram bidireccional**: se puede chatear con el asistente por texto y obtener exactamente el **mismo cerebro, las mismas herramientas y la misma memoria** que por voz. Esta equivalencia es la decisión de diseño relevante. Telegram no es un bot recortado ni un atajo de notificaciones: es el mismo asistente expresándose por otra boca. El texto es un canal de primera clase, no un apaño añadido a posteriori.

La ventaja práctica es doble. Como canal de entrada, permite mandar órdenes sin necesidad de estar frente al micrófono. Como canal de salida, da al sistema una vía para alcanzar al usuario cuando este no está en casa. Por seguridad, el canal **solo responde al dueño**: cualquier otro remitente se ignora, lo que evita exponer un cerebro con manos reales a interlocutores no autorizados.

## Enrutado por presencia

Con dos canales de salida —voz y Telegram— el sistema necesita decidir **por dónde** hablar en cada momento. La regla es de presencia y la resuelve el orquestador, que mantiene un estado vivo *presente/ausente*:

- **Presente** (el usuario está en casa) → **voz**.
- **Ausente** (fuera) → **Telegram**.
- **Noche o no molestar** → **Telegram silencioso**.

La lógica de fondo es sencilla: no se le habla por voz a una casa vacía, ni a gritos a las tres de la madrugada. Un encargo que termina mientras el usuario está en el salón se anuncia en voz alta; el mismo encargo terminado mientras está en la calle le llega al móvil.

Dos detalles hacen robusto este enrutado. El primero cierra el círculo desde el otro extremo: **un mensaje de Telegram se interpreta como «no está delante»**. Quien escribe por texto, por definición, no está frente al micrófono, así que el sistema conmuta a *ausente* al recibirlo. El segundo es un *fail-safe*: el subsistema de visión que alimenta la presencia real todavía está apagado a falta de cámara, de modo que, **ante la ausencia de sensores o un fallo, el sistema asume PRESENTE**. Asumir presencia equivale al comportamiento de toda la vida —responder por voz—, así que el asistente nunca se queda mudo por una avería del subsistema que precisamente aún no existe.

## Tareas programadas: cron en lenguaje natural

La última pieza extiende la proactividad al tiempo: el sistema permite programar trabajo recurrente **dicho en lenguaje natural** («cada mañana dame el tiempo»), sin que el usuario tenga que conocer la sintaxis de un cron clásico. Hay dos sabores con comportamientos distintos:

- **Tareas recurrentes** — se ejecutan y entregan su resultado siempre. La del ejemplo da el parte del tiempo cada mañana, sin excepción.
- **Monitores** — se ejecutan periódicamente pero **solo avisan si hay algo que decir**; cuando no, callan. El patrón es explícito: el prompt del monitor emite un marcador `[SILENT]` que el sistema interpreta como «no molestar esta vez». El monitor es, en esencia, la aplicación del silencio por defecto al dominio temporal.

La decisión de seguridad que sostiene todo el mecanismo es de raíz: el cron **no ejecuta scripts arbitrarios**. Lo que programa son **prompts con herramientas restringidas** —las mismas del catálogo— y no comandos de shell sueltos. La diferencia es sustancial en términos de superficie de ataque: si una tarea programada pudiera lanzar shell libre, cada entrada de cron sería una vía de ejecución arbitraria que sobrevive en el tiempo. Al obligar a que toda tarea se exprese como un prompt sobre el catálogo de herramientas, el trabajo programado queda dentro del mismo perímetro de seguridad y de confirmación que cualquier otra acción del sistema, sin abrir un canal privilegiado paralelo.
