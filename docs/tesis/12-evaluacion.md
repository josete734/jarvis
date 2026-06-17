# Evaluación y resultados

## Metodología de evaluación

La evaluación parte de una premisa de honestidad metodológica: el proyecto es un sistema doméstico de un único usuario, no un producto sometido a *benchmarking* formal. En consecuencia, conviene distinguir desde el inicio entre **lo medido** —cifras obtenidas con instrumentación o cronometraje directo durante las sesiones de validación— y **lo presupuestado/estimado** —objetivos del plan que sirven de referencia pero que no se han verificado de forma cuantitativa exhaustiva en condiciones controladas y repetidas.

Se evalúan cuatro dimensiones: **latencia** del pipeline de voz (descompuesta por etapa), **consumo de recursos** (RAM sobre el host real), **coste económico** (suscripción del modelo, servicios locales y electricidad) y **fiabilidad** (cobertura de la suite de pruebas automáticas más la verificación funcional en vivo de cada subsistema). La latencia y la RAM se midieron sobre el hardware definitivo durante las sesiones de validación; el coste se estima a partir de los precios conocidos; la fiabilidad se evalúa por cobertura de pruebas, no por métricas estadísticas de tasa de error en producción.

## Latencia del pipeline de voz

El pipeline encadena cinco etapas: detección de palabra de activación, detección de fin de turno (VAD + *smart-turn*), transcripción (STT), inferencia del modelo de lenguaje (LLM) y síntesis de voz (TTS). La tabla compara el presupuesto con los datos reales disponibles.

| Etapa | Presupuesto / referencia | Dato real | Origen |
|---|---|---|---|
| Wake word | Disparo fiable, sin falsos positivos | Confianza **0,99** («hey Mycroft») | Medido, en vivo |
| Fin de turno (VAD + smart-turn) | ~200 ms; smart-turn 12–95 ms CPU | No cronometrado aislado E2E | Estimado (config. fijada) |
| STT (faster-whisper *small* INT8) | Casi tiempo real | Español «casi perfecto»; latencia no aislada | Cualitativo |
| LLM (TTFB) | ~0,5 s objetivo | **0,49 s** con Groq; **1,5–8 s** con OpenCode/GLM-5 | Medido (Groq) / observado (OpenCode) |
| TTS (Piper) | < 2 s | **1,8 s** | Medido |

El dato más relevante —y más honesto de reconocer— es la **variabilidad del LLM**. La medición de 0,49 s de tiempo hasta el primer *token* (TTFB) corresponde a la configuración original con Groq. Tras agotar su cupo, el cerebro definitivo pasó a **GLM-5 vía OpenCode Go**, una pasarela remota cuya latencia oscila entre **1,5 y 8 segundos** por enrutarse a regiones distintas. Esta cifra es una **observación de rango**, no una medición controlada con percentiles. Las etapas locales (wake, VAD, STT, TTS) son deterministas y rápidas; el único componente con cola pesada y dependiente de la red es la inferencia remota. No se ha construido una medición E2E «boca-a-oído» agregada y repetida, por lo que no puede afirmarse una latencia total única.

## Consumo de recursos

El host es un Lenovo ThinkCentre M70q con **i5-10400T (35 W de TDP), 16 GB de RAM y sin GPU dedicada**. La configuración con faster-whisper *small* ocupa **aproximadamente 6–6,5 GB de RAM**, dejando un margen amplio sobre los 16 GB disponibles. El escenario previsto de ~8 GB asociado a parakeet no llegó a materializarse, al descartarse ese STT por ser solo en inglés.

La conclusión sobre idoneidad del hardware es favorable y está respaldada por el funcionamiento real: una máquina de bajo consumo sostiene el pipeline completo de voz porque la carga pesada —la inferencia del LLM— se externaliza a la nube, y la visión (cuando se active) se calcula en la iGPU. El margen de RAM permite, además, alojar los servicios auxiliares sin presión de memoria. Debe matizarse que esta medida es un valor de ocupación observado y no un perfilado bajo carga máxima sostenida.

## Coste económico

El coste mensual es deliberadamente bajo:

| Partida | Coste | Naturaleza |
|---|---|---|
| LLM (OpenCode Go) | Suscripción (límites holgados para voz) | Externo |
| Visión y búsquedas (SearXNG propio) | Céntimos | Local |
| Electricidad (host 35 W) | ~2–4 €/mes | Estimado |

El coste de *tokens* dejó de ser una preocupación al pasar a suscripción, frente al modelo de pago por uso. La cifra eléctrica es una **estimación** derivada del TDP, no una lectura con vatímetro. El balance es muy favorable cuando se contrapone al **valor de la privacidad y el control**: el audio, la memoria y las búsquedas se procesan en infraestructura propia, y solo el texto destinado al LLM sale a la nube.

## Calidad y fiabilidad

La fiabilidad se evaluó por dos vías complementarias. La primera es una **suite de 68 pruebas automáticas** que cubre el cron en lenguaje natural, el clasificador y manejo de errores del LLM, la lógica de *routing* por presencia, el registro de herramientas y el almacén de hechos (`facts`) con su lógica de *recall*/*decay*. La segunda es la **verificación funcional en vivo** de todos los subsistemas: conversación completa por voz validada de extremo a extremo, panel en producción tras Cloudflare Access, Telegram bidireccional, delegación de acciones con el guardia de comandos comprobado en vivo, y la memoria con recall/decay.

Conviene ser preciso sobre el alcance: son **pruebas funcionales y de unidad** que verifican comportamiento correcto e invariantes de seguridad (por ejemplo, que el guardia determinista bloquea `rm -rf /`, `mkfs` o `dd`), no pruebas de carga ni de regresión de latencia.

## Limitaciones del estudio

La evaluación presenta limitaciones que es obligado reconocer:

1. **Validación funcional, no cuantitativa exhaustiva.** Se demuestra que el sistema *funciona* end-to-end y que cada subsistema cumple su cometido, pero no existen mediciones estadísticas (medias, percentiles, desviaciones) de latencia ni de tasa de error sobre un volumen amplio de interacciones.
2. **Latencia del LLM no caracterizada.** El rango 1,5–8 s con OpenCode es una observación, no una distribución medida; depende de una pasarela remota fuera del control del proyecto.
3. **Un solo usuario y un solo entorno.** Todas las observaciones provienen del uso del propietario en una única vivienda; no hay validación con múltiples hablantes, acentos ni condiciones acústicas variadas.
4. **Visión pendiente de hardware.** El subsistema de presencia está construido y sus modelos validados, pero permanece apagado a la espera de la cámara física, por lo que sus métricas **no se han medido en operación real**.

En síntesis, el sistema supera con holgura sus presupuestos de recursos y coste, cumple los objetivos de latencia en las etapas locales y queda condicionado, en latencia total, por la pasarela remota del LLM; su fiabilidad está respaldada por cobertura de pruebas más verificación en vivo, a falta de una campaña de medición cuantitativa que queda como trabajo futuro.
