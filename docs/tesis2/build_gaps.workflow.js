export const meta = {
  name: 'tesis-huecos',
  description: 'Añade 6 secciones para cerrar los huecos detectados por el crítico (legal, IA-eval, interop, migración, humano, energía)',
  phases: [ { title: 'Redacción', detail: '6 secciones' }, { title: 'Verificación', detail: '6 revisiones' } ],
}

const SEC = '/opt/jarvis/docs/tesis2/sections'
const REF = SEC + '/95-referencias.md'

const STYLE = `Registro académico riguroso pero legible; voz impersonal ("se argumenta", "conviene", "cabe distinguir"), nunca primera persona ni tono de blog. Terminología consistente (self-hosting/autoalojamiento, local-first, soberanía digital, agencia agéntica, homelab). Citas como (Autor, año) SOLO desde la bibliografía del fichero ${REF} (léelo); no inventes fuentes. Hilo conductor: la IA agéntica local dentro del panorama amplio del self-hosting. El caso «Jarvis» NO se menciona fuera de su capítulo. Markdown limpio para LaTeX: encabezados ## y ###, listas simples, énfasis; sin tablas complejas, HTML ni bloques de código largos.`

const NEW = [
  { f: '18-legal.md', ch: 'Fundamentos: soberanía, datos y el problema de la nube', w: 1000,
    t: 'Marco legal y regulatorio: RGPD, residencia de datos y NIS2',
    brief: 'La soberanía digital como concepto jurídico además de técnico: RGPD/GDPR y autodeterminación informativa; residencia y jurisdicción de los datos; cómo el self-hosting reconfigura los roles de responsable y encargado del tratamiento; NIS2 y obligaciones de seguridad; límites legales del autoalojamiento (correo, menores, datos de terceros).' },
  { f: '285-ia-eval.md', ch: 'Panorama del self-hosting', w: 1000,
    t: 'Evaluación de la IA local: calidad, latencia y límites del hardware',
    brief: 'Cómo medir un LLM local: calidad (benchmarks, evaluación por tareas), latencia (TTFB, tokens/s), memoria; compromisos de la cuantización (precisión vs. tamaño); métricas de STT (WER) y TTS; límites reales del hardware de consumo sin GPU dedicada; criterio para decidir cuándo la IA local es suficiente frente a delegar a la nube.' },
  { f: '29-interop.md', ch: 'Panorama del self-hosting', w: 1000,
    t: 'Interoperabilidad y protocolos abiertos',
    brief: 'Los estándares abiertos como condición de la soberanía: ActivityPub y el fediverso, federación de Matrix, CalDAV/CardDAV, IMAP/SMTP, y el emergente MCP para herramientas de IA agéntica; formatos abiertos y portabilidad; interoperabilidad frente a jardines vallados; por qué un protocolo abierto vale más que una característica.' },
  { f: '39-migracion.md', ch: 'Arquitectura y operación', w: 1000,
    t: 'Migración: entrar y salir de la nube y entre soluciones',
    brief: 'Estrategias para migrar DESDE la nube (exportación de datos, Takeout, APIs, derecho a la portabilidad del RGPD) y entre soluciones autoalojadas; planificación, ventanas de corte y validación; verificación de integridad; el lock-in como riesgo operativo y cómo el diseño con formatos abiertos lo previene.' },
  { f: '715-humano.md', ch: 'Discusión y futuro', w: 1000,
    t: 'El factor humano: carga operativa, aprendizaje y factor bus',
    brief: 'La dimensión social y sostenible del self-hosting: curva de aprendizaje y carga operativa continuada; el "factor bus" (qué ocurre cuando el administrador no está); usuarios no técnicos y la familia como dependientes del servicio; documentación, traspaso y planes de sucesión; la soberanía como responsabilidad además de derecho.' },
  { f: '716-energia.md', ch: 'Discusión y futuro', w: 900,
    t: 'Energía y huella ambiental',
    brief: 'El coste energético de un homelab 24/7 frente a la eficiencia de la hiperescala; huella de fabricación y la segunda mano como mitigación; hardware de bajo consumo; el equilibrio honesto entre soberanía y sostenibilidad ambiental; medir el consumo y dimensionar con criterio.' },
]

const DRAFT = { type: 'object', additionalProperties: false, properties: { written: { type: 'boolean' }, words: { type: 'integer' } }, required: ['written', 'words'] }
const VER = { type: 'object', additionalProperties: false, properties: { words: { type: 'integer' }, notes: { type: 'string' } }, required: ['words', 'notes'] }

const draftPrompt = (s) => `Eres redactor académico experto de la tesis en español de España «Cómputo soberano» (self-hosting / cómputo soberano; hilo = IA agéntica local).
GUÍA DE ESTILO: ${STYLE}
CAPÍTULO: «${s.ch}»
SECCIÓN: «${s.t}»
DEBE CUBRIR: ${s.brief}
EXTENSIÓN: ~${s.w} palabras.
Lee primero ${REF} para citar (Autor, año) solo de ahí. Empieza EXACTAMENTE con "## ${s.t}" (sin encabezado de capítulo). Prosa rigurosa con matices y ejemplos; nada de relleno. Guarda con Write en ${SEC}/${s.f}. Devuelve {written:true, words:<n>}.`

const verifyPrompt = (s) => `Eres revisor académico adversarial de «Cómputo soberano». Lee ${SEC}/${s.f} (sección «${s.t}», capítulo «${s.ch}»). Corrige y mejora reescribiendo el fichero con Write: rigor y exactitud (elimina datos dudosos y citas no presentes en ${REF}); coherencia con la guía (${STYLE}); que empiece por "## ${s.t}"; profundidad ~${s.w} palabras; markdown limpio para LaTeX; el caso «Jarvis» no aparece aquí. Reescribe con Write en ${SEC}/${s.f}. Devuelve {words:<n>, notes:"<1 frase>"}.`

const res = await pipeline(NEW,
  (s) => agent(draftPrompt(s), { label: `draft:${s.f}`, phase: 'Redacción', effort: 'high', agentType: 'general-purpose', schema: DRAFT }),
  (_d, s) => agent(verifyPrompt(s), { label: `verify:${s.f}`, phase: 'Verificación', effort: 'high', agentType: 'general-purpose', schema: VER }),
)
return { nuevas: res.filter(Boolean).length, total: NEW.length }
