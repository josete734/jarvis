export const meta = {
  name: 'tesis-computo-soberano',
  description: 'Genera una tesis exhaustiva sobre self-hosting ("Cómputo soberano") con ~100 agentes: bibliografía real, 44 secciones redactadas y verificadas, y cohesión',
  phases: [
    { title: 'Cimientos', detail: 'bibliografía real + guía de estilo' },
    { title: 'Redacción', detail: 'un agente por sección (44)' },
    { title: 'Verificación', detail: 'revisión adversarial por sección (44)' },
    { title: 'Cohesión', detail: 'resumen, intro, conclusiones, intros de capítulo, crítica de huecos' },
  ],
}

const DIR = '/opt/jarvis/docs/tesis2'
const SEC = DIR + '/sections'

const CHAPTERS = [
  { key: 'fund', file: '10-cap-fundamentos.md', title: 'Fundamentos: soberanía, datos y el problema de la nube' },
  { key: 'pano', file: '20-cap-panorama.md',    title: 'Panorama del self-hosting' },
  { key: 'arch', file: '30-cap-arquitectura.md', title: 'Arquitectura y operación' },
  { key: 'seg',  file: '40-cap-seguridad.md',    title: 'Seguridad y amenazas' },
  { key: 'gob',  file: '50-cap-gobernanza.md',   title: 'Gobernanza y agencia segura' },
  { key: 'caso', file: '60-cap-caso.md',         title: 'Caso aplicado: un asistente de voz agéntico autoalojado' },
  { key: 'disc', file: '70-cap-discusion.md',    title: 'Discusión y futuro' },
]
const chTitle = (k) => (CHAPTERS.find(c => c.key === k) || {}).title || ''

const SECTIONS = [
  // Fundamentos
  { f: '11-econcloud.md', ch: 'fund', w: 1100, t: 'La economía de la nube: renta, dependencia y vigilancia', brief: 'Modelo de negocio del cloud (renta recurrente, captura de datos, capitalismo de vigilancia); externalidades; por qué "gratis" no lo es; centralización de poder.' },
  { f: '12-soberania.md', ch: 'fund', w: 1000, t: 'Soberanía digital y propiedad de los datos', brief: 'Definición de soberanía digital (individual y colectiva); propiedad/custodia frente a alojamiento; jurisdicción y control efectivo; data ownership.' },
  { f: '13-localfirst.md', ch: 'fund', w: 1100, t: 'El paradigma local-first', brief: 'Los siete principios local-first (Ink & Switch / Kleppmann); CRDTs y sincronización; relación con offline-first y self-hosting; diferencias y solapes.' },
  { f: '14-privacidad.md', ch: 'fund', w: 1000, t: 'Privacidad, confidencialidad y minimización', brief: 'Privacidad como control; minimización de datos; cifrado en reposo/tránsito/extremo a extremo; marco GDPR; superficie de exposición personal.' },
  { f: '15-coste.md', ch: 'fund', w: 1000, t: 'Coste total de propiedad: nube frente a infraestructura propia', brief: 'TCO honesto: hardware, energía, tiempo, fiabilidad; punto de equilibrio; cuándo el cloud es más barato; coste oculto del tiempo humano.' },
  { f: '16-lockin.md', ch: 'fund', w: 900, t: 'Longevidad, lock-in y obsolescencia', brief: 'Vendor lock-in; formatos abiertos; portabilidad; longevidad de los datos personales (décadas); riesgo de discontinuación de servicios.' },
  { f: '17-limites.md', ch: 'fund', w: 900, t: 'Honestidad intelectual: cuándo el self-hosting no compensa', brief: 'Contraargumentos serios: fiabilidad, responsabilidad operativa, seguridad mal hecha es peor, no para todos; criterios para decidir.' },
  // Panorama
  { f: '21-taxonomia.md', ch: 'pano', w: 900, t: 'Una taxonomía de servicios autoalojables', brief: 'Clasificación por dominio y criticidad; servicios de datos vs. de cómputo vs. de IA; criterios de madurez y mantenibilidad.' },
  { f: '22-almacenamiento.md', ch: 'pano', w: 1000, t: 'Almacenamiento y archivos: NAS y Nextcloud', brief: 'NAS, sistemas de ficheros, RAID/ZFS; Nextcloud y sincronización; alternativas (Syncthing, Seafile); fotos y documentos.' },
  { f: '23-media.md', ch: 'pano', w: 900, t: 'Multimedia: Jellyfin y el ecosistema *arr', brief: 'Servidores de medios (Jellyfin/Plex); automatización *arr; transcodificación; consideraciones legales y éticas.' },
  { f: '24-domotica.md', ch: 'pano', w: 1000, t: 'Domótica: Home Assistant y la automatización local', brief: 'Home Assistant; local vs. nube en IoT; protocolos (Zigbee, Matter); privacidad de sensores; automatizaciones; relación con la agencia.' },
  { f: '25-comunicaciones.md', ch: 'pano', w: 900, t: 'Comunicaciones: correo, Matrix y mensajería', brief: 'Self-hosting de correo (dificultad real, reputación IP); Matrix/XMPP; mensajería federada; trade-offs.' },
  { f: '26-conocimiento.md', ch: 'pano', w: 800, t: 'Conocimiento y productividad', brief: 'Wikis, notas (Obsidian/Joplin), marcadores, RSS, gestores; el grafo de conocimiento personal; soberanía del segundo cerebro.' },
  { f: '27-identidad.md', ch: 'pano', w: 900, t: 'Identidad, contraseñas y secretos', brief: 'Gestores de contraseñas (Vaultwarden); SSO doméstico (Authelia/Keycloak); el problema del secreto raíz; identidad propia.' },
  { f: '28-ia-local.md', ch: 'pano', w: 1200, t: 'Inteligencia local: LLMs, voz y visión en casa', brief: 'LLMs locales (cuantización, hardware); STT/TTS/wake-word; visión; el coste/beneficio de la IA agéntica autoalojada; abre el hilo conductor del documento.' },
  // Arquitectura
  { f: '31-hardware.md', ch: 'arch', w: 1100, t: 'Hardware y dimensionamiento; energía', brief: 'Del mini-PC al rack; CPU/RAM/almacenamiento/GPU; consumo y coste energético; ruido y ubicación; segunda mano y sostenibilidad.' },
  { f: '32-contenedores.md', ch: 'arch', w: 1100, t: 'Contenedores y orquestación', brief: 'Docker/Compose como unidad de despliegue; aislamiento; Podman; orquestadores ligeros (k3s, Nomad); cuándo NO usar Kubernetes.' },
  { f: '33-redes.md', ch: 'arch', w: 1000, t: 'Redes domésticas: segmentación, DNS, descubrimiento', brief: 'VLANs y segmentación (IoT aparte); DNS local; descubrimiento de servicios; IPv6; firewall doméstico.' },
  { f: '34-exposicion.md', ch: 'arch', w: 1100, t: 'Exposición segura: reverse proxy, túneles y WireGuard', brief: 'Reverse proxy (Caddy/Traefik/Nginx) + TLS automático; túneles (Cloudflare Tunnel); VPN propia (WireGuard/Tailscale); no abrir puertos sin pensar.' },
  { f: '35-datos.md', ch: 'arch', w: 900, t: 'Datos y estado: bases de datos y persistencia', brief: 'Volúmenes y estado; Postgres/SQLite; migraciones; integridad; el estado como activo crítico frente a contenedores efímeros.' },
  { f: '36-backups.md', ch: 'arch', w: 1000, t: 'Copias de seguridad y recuperación (3-2-1)', brief: 'Regla 3-2-1; backups cifrados (restic/borg); off-site; pruebas de restauración; RPO/RTO domésticos; el backup no probado no existe.' },
  { f: '37-observabilidad.md', ch: 'arch', w: 1000, t: 'Observabilidad: logs, métricas y salud', brief: 'Logs centralizados; métricas (Prometheus/Grafana); alertas; healthchecks; uptime; observabilidad proporcionada al homelab.' },
  { f: '38-iac.md', ch: 'arch', w: 1000, t: 'Reproducibilidad e infraestructura como código', brief: 'Configuración declarativa; GitOps doméstico; Ansible/compose en git; reproducir el homelab tras un desastre; documentación como código.' },
  // Seguridad
  { f: '41-amenazas.md', ch: 'seg', w: 1100, t: 'Modelo de amenazas del homelab', brief: 'Adversarios realistas (escaneo masivo, ransomware, insider, IoT comprometido); activos a proteger; STRIDE adaptado; riesgo proporcional.' },
  { f: '42-superficie.md', ch: 'seg', w: 1000, t: 'Superficie de ataque y exposición a Internet', brief: 'Qué se expone y por qué; puertos, servicios, paneles; shodan; principio de no exponer; DMZ doméstica.' },
  { f: '43-hardening.md', ch: 'seg', w: 1100, t: 'Endurecimiento: mínimo privilegio y aislamiento', brief: 'Mínimo privilegio; usuarios no-root en contenedores; capabilities; seccomp/AppArmor; aislamiento entre servicios; superficie mínima.' },
  { f: '44-secretos.md', ch: 'seg', w: 1000, t: 'Gestión de secretos y credenciales', brief: 'El .env monolítico como antipatrón; secretos por servicio/scope; rotación; bóvedas; secretos en git (cómo evitarlo); fugas.' },
  { f: '45-zerotrust.md', ch: 'seg', w: 1000, t: 'Identidad, autenticación y zero-trust', brief: 'Autenticación fuerte (MFA, passkeys); zero-trust/BeyondCorp llevado al hogar; proxy de identidad; no confiar en la LAN por defecto.' },
  { f: '46-supplychain.md', ch: 'seg', w: 900, t: 'Cadena de suministro y parches', brief: 'Imágenes de contenedor de confianza; firmas; actualizaciones automáticas vs. controladas; CVEs; dependencias; renovate/watchtower con criterio.' },
  { f: '47-ia-vectores.md', ch: 'seg', w: 1200, t: 'IA local: prompt injection, exfiltración y agencia', brief: 'Nuevos vectores de la IA agéntica: prompt injection (Greshake et al.), exfiltración vía herramientas, confused deputy; por qué la agencia amplía el riesgo; conecta con el cap. de gobernanza.' },
  { f: '48-resiliencia.md', ch: 'seg', w: 800, t: 'Continuidad y resiliencia', brief: 'Fallos de hardware, energía (SAI), disco; degradación elegante; plan de recuperación; la fiabilidad como cara B de la seguridad.' },
  // Gobernanza
  { f: '51-agencia.md', ch: 'gob', w: 1100, t: 'De la automatización a la agencia', brief: 'Diferencia entre automatización determinista y agencia (IA que decide y actúa); espectro de autonomía; por qué la IA local doméstica cruza esa línea.' },
  { f: '52-riesgos-agencia.md', ch: 'gob', w: 1100, t: 'Riesgos de la agencia: permisos y acciones irreversibles', brief: 'Acciones con efectos en el mundo (borrar, gastar, enviar); irreversibilidad; sobre-permisos; el agente como diputado confundido; necesidad de límites.' },
  { f: '53-contencion.md', ch: 'gob', w: 1200, t: 'Patrones de contención: confirmación, capabilities y sandboxing', brief: 'Confirmación humana; capabilities declarativas fail-closed; sandboxing (worktrees, contenedores); credenciales efímeras (JWT por run); deny-lists; defensa en profundidad.' },
  { f: '54-trazabilidad.md', ch: 'gob', w: 1100, t: 'Trazabilidad: auditoría inmutable, aprobaciones y rollback', brief: 'Registro de auditoría inmutable; colas de aprobación; revisiones reversibles/rollback; por qué la trazabilidad es condición de la agencia segura.' },
  { f: '55-datos-aprendizaje.md', ch: 'gob', w: 1000, t: 'Gobernanza del dato y del aprendizaje', brief: 'Memoria de la IA (qué recuerda/olvida); consentimiento; decaimiento y archivo; aprendizaje supervisado por el usuario; propuestas que el humano aprueba.' },
  { f: '56-humano-bucle.md', ch: 'gob', w: 900, t: 'El humano en el bucle', brief: 'Diseño centrado en humano; cuándo pedir permiso; presencia/contexto; transparencia; explicabilidad de las acciones; confianza calibrada.' },
  // Caso aplicado (Jarvis) — llevado a cabo, NO núcleo
  { f: '61-caso-contexto.md', ch: 'caso', w: 900, t: 'Contexto, objetivos y restricciones', brief: 'Presenta el caso como ILUSTRACIÓN del marco, no como núcleo: un asistente de voz agéntico autoalojado en hardware de consumo; objetivos (privacidad, agencia, español); restricciones reales.' },
  { f: '62-caso-arquitectura.md', ch: 'caso', w: 1200, t: 'Arquitectura del asistente', brief: 'Voz local (wake-word, STT, TTS); cerebro LLM; herramientas; canal de texto (Telegram); orquestación en contenedores; cómo encarna los principios de los capítulos previos.' },
  { f: '63-caso-agencia.md', ch: 'caso', w: 1200, t: 'Agencia segura en la práctica', brief: 'Delegación de acciones con confirmación; guardián/deny-list; sudo acotado; auditoría inmutable + rollback; reposo de recursos; prompt injection mitigado; ejemplo concreto de los patrones de contención del cap. de gobernanza.' },
  { f: '64-caso-lecciones.md', ch: 'caso', w: 1000, t: 'Resultados y lecciones aprendidas', brief: 'Qué valida del marco y qué lo tensiona; latencia/fiabilidad; coste; honestidad sobre límites; generalización a otros despliegues self-hosted.' },
  // Discusión
  { f: '71-tensiones.md', ch: 'disc', w: 1000, t: 'Tensiones del self-hosting', brief: 'Esfuerzo y mantenimiento; fiabilidad frente a hiperescala; energía; brecha de habilidad; el riesgo de seguridad mal hecha; sostenibilidad del modelo.' },
  { f: '72-hibridos.md', ch: 'disc', w: 900, t: 'Modelos híbridos y estrategias de adopción', brief: 'No es todo-o-nada: híbridos (datos en casa, cómputo puntual fuera); adopción gradual; comunidad y conocimiento compartido; soberanía pragmática.' },
  { f: '73-futuro.md', ch: 'disc', w: 1000, t: 'El futuro: IA local, hardware y comunidad', brief: 'Tendencias: IA local cada vez más capaz; hardware accesible (NPUs); regulación (soberanía de datos); movimiento self-hosted; visión a 5-10 años.' },
]

// ---- esquemas -------------------------------------------------------------
const SOURCES_SCHEMA = { type: 'object', additionalProperties: false,
  properties: { refs: { type: 'array', items: { type: 'object', additionalProperties: false,
    properties: { key: { type: 'string' }, cite: { type: 'string' } }, required: ['key', 'cite'] } } },
  required: ['refs'] }
const DRAFT_SCHEMA = { type: 'object', additionalProperties: false,
  properties: { written: { type: 'boolean' }, words: { type: 'integer' } }, required: ['written', 'words'] }
const VERIFY_SCHEMA = { type: 'object', additionalProperties: false,
  properties: { words: { type: 'integer' }, notes: { type: 'string' } }, required: ['words', 'notes'] }
const CRITIC_SCHEMA = { type: 'object', additionalProperties: false,
  properties: { gaps: { type: 'array', items: { type: 'string' } }, overlaps: { type: 'array', items: { type: 'string' } } },
  required: ['gaps', 'overlaps'] }

const OUTLINE = CHAPTERS.map(c => `# ${c.title}\n` +
  SECTIONS.filter(s => s.ch === c.key).map(s => `  - ${s.t}`).join('\n')).join('\n')

// ---- Fase 1: cimientos ----------------------------------------------------
phase('Cimientos')
const SOURCES_PROMPT = `Eres documentalista académico. Compila una bibliografía REAL y verificable (30-40 referencias canónicas) para una tesis en español sobre self-hosting, cómputo soberano, local-first e IA agéntica local. Cubre al menos: local-first software (Kleppmann / Ink & Switch, 2019), CRDTs, soberanía y propiedad de datos, privacidad y GDPR, capitalismo de vigilancia (Zuboff), seguridad (NIST, principio de mínimo privilegio, zero-trust / BeyondCorp de Google), contenedores (Docker), redes (WireGuard de Donenfeld), teorema CAP (Brewer), bases de datos, IA agéntica y prompt injection (Greshake et al., 2023), Home Assistant, Nextcloud, restic/borg, RFCs y estándares pertinentes.
REGLA DURA: SOLO fuentes reales que conozcas con certeza (autores/obras famosas, papers conocidos, RFCs, estándares, documentación oficial). NO inventes títulos, autores ni años. Si dudas de una, no la incluyas.
Escribe el fichero ${SEC}/95-referencias.md con el encabezado exacto "# Referencias {.unnumbered}" seguido de la lista ordenada alfabéticamente, en formato legible (Autor(es) (año). *Título*. Editorial/Publicación. URL si aplica).
Devuelve {refs:[{key:"(Autor, año)", cite:"cita completa"}]} con todas las referencias.`

const STYLE_PROMPT = `Eres editor jefe de una tesis académica en español de España: «Cómputo soberano: servicios, datos e inteligencia agéntica en infraestructura propia». Redacta una GUÍA DE ESTILO concisa (máx. 500 palabras) que seguirán 44 redactores para lograr un documento coherente y de nivel. Incluye decisiones sobre: registro (académico riguroso pero legible, sin jerga gratuita); voz impersonal ("se argumenta", "conviene", "cabe distinguir"), nada de primera persona ni tono de blog; terminología consistente (self-hosting/autoalojamiento, local-first, soberanía digital, agencia agéntica, homelab); uso de citas como (Autor, año) SOLO desde la bibliografía provista, sin inventar; el HILO CONDUCTOR es la IA agéntica local insertada dentro del panorama amplio del self-hosting (no monográfico de IA); el CASO PRÁCTICO (asistente de voz "Jarvis") aparece EXCLUSIVAMENTE en su capítulo, como ilustración del marco, jamás como núcleo ni en otros capítulos; densidad (cada sección aporta, sin relleno); markdown limpio compatible con LaTeX/pandoc (encabezados, listas simples, énfasis; NADA de tablas complejas, HTML ni bloques de código largos). Devuelve solo la guía, en texto plano.`

const [sources, styleGuide] = await parallel([
  () => agent(SOURCES_PROMPT, { label: 'bibliografía', phase: 'Cimientos', schema: SOURCES_SCHEMA, agentType: 'general-purpose' }),
  () => agent(STYLE_PROMPT, { label: 'guía de estilo', phase: 'Cimientos' }),
])
const sourcesText = (sources && sources.refs ? sources.refs : []).map(r => `- ${r.key}: ${r.cite}`).join('\n')
log(`Cimientos listos: ${(sources && sources.refs ? sources.refs.length : 0)} referencias`)

// ---- Fases 2-3: redacción + verificación (pipeline, sin barrera) ----------
const draftPrompt = (s) => `Eres redactor académico experto. Documento: tesis en español de España «Cómputo soberano» (self-hosting / cómputo soberano; hilo conductor = IA agéntica local).
GUÍA DE ESTILO (acátala):
${styleGuide}
BIBLIOGRAFÍA disponible (cita SOLO de aquí, como (Autor, año); NO inventes fuentes):
${sourcesText}
CAPÍTULO: «${chTitle(s.ch)}»
SECCIÓN A ESCRIBIR: «${s.t}»
DEBE CUBRIR: ${s.brief}
EXTENSIÓN: ~${s.w} palabras.
INSTRUCCIONES:
- Empieza EXACTAMENTE con el encabezado de nivel 2: "## ${s.t}". No incluyas el encabezado del capítulo (nivel 1).
- Prosa académica rigurosa, con matices, ejemplos concretos y comparativas; nada de relleno ni de obviedades.
- Cita (Autor, año) cuando aporte, solo de la bibliografía dada.
- El caso «Jarvis» NO se menciona aquí ${s.ch === 'caso' ? '(salvo que esta sección sea del capítulo del caso aplicado, que lo es)' : '(esta sección NO es del capítulo del caso: no lo nombres)'}.
- Markdown limpio para LaTeX: encabezados ## y ###, listas simples y énfasis; sin tablas complejas, HTML ni bloques de código largos.
- Guarda el resultado con la herramienta Write en el fichero: ${SEC}/${s.f}
Devuelve {written:true, words:<nº de palabras escritas>}.`

const verifyPrompt = (s) => `Eres revisor académico adversarial y editor de la tesis «Cómputo soberano». Abre y lee el fichero ${SEC}/${s.f} (sección «${s.t}» del capítulo «${chTitle(s.ch)}»).
CORRIGE y MEJORA reescribiendo el propio fichero con Write:
- Rigor y exactitud: elimina afirmaciones dudosas, datos inventados y CITAS que no estén en la bibliografía o parezcan fabricadas.
- Coherencia con la guía de estilo (voz impersonal, terminología, registro).
- Que empiece por "## ${s.t}" y NO incluya encabezado de capítulo.
- Profundidad y longitud (~${s.w} palabras): amplía si está flojo, poda si divaga.
- Markdown limpio para LaTeX (sin tablas complejas/HTML/bloques de código largos).
- Que el caso «Jarvis» ${s.ch === 'caso' ? 'se exponga con claridad como ilustración del marco' : 'NO aparezca (esta sección no es del capítulo del caso)'}.
BIBLIOGRAFÍA válida:
${sourcesText}
GUÍA DE ESTILO:
${styleGuide}
Reescribe el fichero corregido con Write en ${SEC}/${s.f}. Devuelve {words:<nº final>, notes:"<1 frase de qué corregiste>"}.`

const results = await pipeline(SECTIONS,
  (s) => agent(draftPrompt(s), { label: `draft:${s.f}`, phase: 'Redacción', effort: 'high', agentType: 'general-purpose', schema: DRAFT_SCHEMA }),
  (_d, s) => agent(verifyPrompt(s), { label: `verify:${s.f}`, phase: 'Verificación', effort: 'high', agentType: 'general-purpose', schema: VERIFY_SCHEMA }),
)
const okSections = results.filter(Boolean).length
log(`Secciones redactadas y verificadas: ${okSections}/${SECTIONS.length}`)

// ---- Fase 4: cohesión -----------------------------------------------------
phase('Cohesión')
const chapIntro = (c) => agent(
  `Eres editor de la tesis «Cómputo soberano». Escribe la PORTADILLA del capítulo «${c.title}». GUÍA DE ESTILO:\n${styleGuide}\nEl capítulo contendrá estas secciones:\n${SECTIONS.filter(s => s.ch === c.key).map(s => '- ' + s.t).join('\n')}\nEscribe con Write en ${SEC}/${c.file}: el encabezado de nivel 1 exacto "# ${c.title}" seguido de 2-3 párrafos que enmarquen el capítulo, su tesis y lo que el lector encontrará, conectando con el hilo de la IA agéntica local cuando proceda. Markdown limpio. Devuelve "ok".`,
  { label: `intro:${c.key}`, phase: 'Cohesión' })

const front = [
  () => agent(`Eres editor de la tesis «Cómputo soberano: servicios, datos e inteligencia agéntica en infraestructura propia» (José Ángel Castillo Díez, 2026). Escribe el RESUMEN/abstract académico (~300 palabras) que sintetice problema, tesis, método, contribuciones y el hilo de la IA agéntica local. Estructura general de la tesis:\n${OUTLINE}\nEscribe con Write en ${SEC}/00-resumen.md, empezando por "# Resumen {.unnumbered}". Devuelve "ok".`, { label: 'resumen', phase: 'Cohesión' }),
  () => agent(`Eres editor de la tesis «Cómputo soberano». Escribe la INTRODUCCIÓN (~1200 palabras): el problema (dependencia de la nube), la pregunta y tesis central (soberanía mediante self-hosting; la IA agéntica local como frontera), el alcance, la metodología (investigación + caso aplicado), y la estructura del documento. GUÍA DE ESTILO:\n${styleGuide}\nEstructura:\n${OUTLINE}\nEscribe con Write en ${SEC}/05-introduccion.md, empezando por "# Introducción". Markdown limpio. Devuelve "ok".`, { label: 'introducción', phase: 'Cohesión', effort: 'high' }),
  () => agent(`Eres editor de la tesis «Cómputo soberano». Escribe las CONCLUSIONES (~1000 palabras): síntesis de los hallazgos, contribuciones, qué aporta el caso aplicado al marco, límites honestos y líneas futuras. GUÍA DE ESTILO:\n${styleGuide}\nEstructura:\n${OUTLINE}\nEscribe con Write en ${SEC}/90-conclusiones.md, empezando por "# Conclusiones". Devuelve "ok".`, { label: 'conclusiones', phase: 'Cohesión', effort: 'high' }),
]

await parallel([...CHAPTERS.map(c => () => chapIntro(c)), ...front])

const critic = await agent(
  `Eres crítico editorial de la tesis «Cómputo soberano». Esta es su estructura completa (capítulos y secciones):\n${OUTLINE}\nDado el ángulo (investigativo equilibrado: por qué / cómo / riesgos), el panorama amplio de self-hosting con la IA agéntica local como hilo y el caso Jarvis solo como ilustración: identifica HUECOS de cobertura (temas importantes ausentes) y SOLAPES/redundancias entre secciones. Devuelve {gaps:[...], overlaps:[...]} (listas breves, máximo 8 cada una).`,
  { label: 'crítica-huecos', phase: 'Cohesión', schema: CRITIC_SCHEMA, effort: 'high' })

return {
  title: 'Cómputo soberano',
  secciones_ok: okSections,
  total_secciones: SECTIONS.length,
  referencias: (sources && sources.refs ? sources.refs.length : 0),
  huecos: (critic && critic.gaps) || [],
  solapes: (critic && critic.overlaps) || [],
}
