# Metodología y materiales

## Enfoque metodológico

El proyecto se aborda mediante una metodología de **investigación a través del diseño** (*research through design*), en la que el conocimiento se produce construyendo, observando y refinando un artefacto real. No se trata de validar una hipótesis aislada en condiciones de laboratorio, sino de demostrar la **viabilidad** de un sistema completo bajo restricciones realistas y de extraer, del proceso de construcción, principios de diseño transferibles. Este enfoque es habitual en la ingeniería de sistemas, donde la integración de componentes —y no cada componente por separado— constituye el problema central.

El desarrollo siguió un ciclo **iterativo e incremental** organizado en fases, cada una con un criterio de éxito verificable. Una decisión metodológica importante condicionó todo el proceso: las fases se materializan como **interruptores de configuración, no como ramas de código**. El código de funcionalidades futuras convive, desactivado, con el de las activas, de modo que avanzar consiste en encender un flag y validar. Esta disciplina permitió ejecutar fases fuera de orden cuando convenía y, sobre todo, mantener en todo momento un sistema arrancable y demostrable.

La validación combinó tres instrumentos: **pruebas automáticas** (unitarias y de seguridad) que protegen los invariantes críticos frente a regresiones; **verificación funcional en vivo** de cada subsistema sobre el hardware definitivo; y un **diario de laboratorio** por sesiones que documenta decisiones, incidencias y su resolución, garantizando la trazabilidad del razonamiento de diseño.

## Materiales: hardware

El sistema se construyó sobre un **Lenovo ThinkCentre M70q Tiny**, un mini-PC de sobremesa de bajo consumo elegido por representar el segmento de *hardware de consumo asequible* que el objetivo exige. Sus características relevantes son un procesador Intel Core i5-10400T (6 núcleos, 12 hilos, 35 W de potencia de diseño térmico), 16 GB de RAM, una unidad NVMe para el sistema y los modelos, y la gráfica integrada Intel UHD 630. La ausencia de GPU dedicada es deliberada: condiciona la arquitectura hacia el modelo híbrido y demuestra que la solución no exige una inversión especializada.

Para la captura y reproducción de audio se empleó un **Anker PowerConf**, un altavoz de conferencia USB con cancelación de eco por hardware, cuya elección se justifica en el capítulo del pipeline de voz. La cámara para el subsistema de visión es una webcam USB estándar, pendiente de integración física en el momento de redacción.

## Materiales: software y stack tecnológico

La solución se compone íntegramente de **software libre y de servicios bajo control del usuario**, orquestados como un conjunto de contenedores mediante Docker Compose con versiones fijadas para garantizar la reproducibilidad. Las piezas principales son Pipecat como marco de orquestación de voz en tiempo real; openWakeWord para la palabra de activación; faster-whisper para el reconocimiento de voz; Piper para la síntesis; LiteLLM como pasarela hacia el modelo de lenguaje; SearXNG como metabuscador privado; SQLite (con su extensión de búsqueda de texto completo FTS5) como almacén de memoria; y OpenVINO con YOLO11n e InsightFace para la visión. La tabla de versiones exactas se recoge en el Anexo correspondiente.

## Criterios de diseño

Cinco criterios, enunciados al inicio y sostenidos a lo largo del proyecto, guiaron cada decisión:

1. **Local-first.** Lo sensible a privacidad y latencia se ejecuta en local por defecto; la nube es un complemento acotado, no el centro del sistema.
2. **Privilegio mínimo y fail-closed.** Cada componente recibe el mínimo privilegio necesario, y ante la duda o el error el sistema deniega en lugar de permitir.
3. **Determinismo en las barreras críticas.** La seguridad que importa reside en código verificable, nunca en el comportamiento de un modelo probabilístico.
4. **Sustituibilidad.** Las piezas se desacoplan tras interfaces estables (la pasarela de LLM, el backend de reconocimiento, el registro de herramientas) para no quedar atados a un proveedor o una librería.
5. **Honestidad y reproducibilidad.** Las decisiones, las versiones y las limitaciones se documentan; se distingue explícitamente lo medido de lo estimado.

## Reproducibilidad

Todo el código y la documentación residen en un repositorio público bajo control de versiones. Los secretos se mantienen fuera del repositorio mediante ficheros de entorno excluidos del control de versiones, de modo que clonar el proyecto no expone ninguna credencial. Los modelos y los datos de usuario viven fuera del árbol del repositorio. Esta organización permite que un tercero reconstruya el sistema desde cero siguiendo el manual de operación incluido como anexo.
