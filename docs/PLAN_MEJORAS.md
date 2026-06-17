# Plan de mejoras Jarvis — robado de OpenClaw + Hermes (2026-06-17)

Análisis línea-a-línea de `/home/jose/repos/{openclaw,hermes-agent}` cruzado con lo que
Jarvis YA tiene. Cada ítem: origen real, gap, archivos a tocar, esfuerzo (S/M/L), riesgo.
Ordenado por bloques con dependencias. **Leyenda prioridad:** 🔴 alta · 🟠 media · ⚪ baja.

---

## BLOQUE 1 · Seguridad de la delegación (`encargar`/sudo) — 🔴 EMPEZAR AQUÍ

> Acabamos de dar a Claude Code sudo (docker/systemctl/apt) con SOLO una confirmación
> binaria. Hoy la seguridad de la acción depende 100% de que el LLM operador obedezca un
> prompt en español. OpenClaw resuelve esto con enforcement determinista. Esto también
> implementa de hecho la "doble confirmación para lo peligroso" que se pidió.

| # | Tarea | Origen (openclaw) | Archivos Jarvis | Esf | Riesgo |
|---|-------|-------------------|-----------------|:---:|:------:|
| 1.1 | **Allowlist determinista en el bridge `/do`**: regex de comandos permitidos (docker/systemctl/apt + lectura), `argPattern` (apt solo install/update, NO remove/purge), **deny por defecto / fail-closed**. Hook PreToolUse de Claude Code o wrapper-deny. | `exec-allowlist-pattern.ts`, `exec-approvals.md` | `jarvis-research.py` + nuevo `bridge_allowlist.py` | M | medio |
| 1.2 | **Niveles de riesgo en el núcleo**: `request_confirmation` pasa de binario a `safe`/`confirm`/`deny`. Clasificador regex de la tarea/comando: `rm -rf`, `mkfs`, `dd`, `:(){`, `>/dev/`, `chmod -R 777 /` → **deny o doble confirmación**. | `permission-modes.md`, `command-auth.ts` | `security_core.py`, `tools/registry.py`, `tests/test_security.py` | M | bajo |
| 1.3 | **Stricter-wins / host endurece**: el bridge (host, fuera del LLM) aplica SU allowlist como techo, independiente de lo que mande el orquestador. | `exec-approvals-effective.ts` | `jarvis-research.py` | S | bajo |
| 1.4 | (Después) **Plan-then-execute**: `claude --permission-mode plan` → leer el plan concreto a José → ejecutar SOLO ese plan tras el sí (anti-drift "confirmaste una cosa, hizo otra"). | binding canónico `exec-approvals.md:454` | `jarvis-research.py`, `tools/encargar.py` | L | medio |
| 1.5 | (Opcional) **allow-always por patrón** persistente (`actions-approvals.json`), seed manual, NO auto-persistir desde voz. | `exec-approvals.json` | bridge + `/srv/jarvis/` | M | medio |

---

## BLOQUE 2 · Memoria que de verdad aprende — 🔴 (dependencias internas)

> El orden importa: 2.1 (instrumentar recall) habilita 2.5 y 2.6.

| # | Tarea | Origen | Archivos | Esf | Riesgo |
|---|-------|--------|----------|:---:|:------:|
| 2.1 | **Instrumentar recall**: `recordar()` cuenta por hecho `recall_count`, `query_hashes`, `recall_days`, `last_recalled_at` (1 UPDATE por match FTS5). Base de todo ranking/decay. | hermes `skill_usage.bump_use`; openclaw `recordShortTermRecalls` | `tools/memoria.py`, esquema `events.db` | S | bajo |
| 2.2 | **Taxonomía "NO capturar"** en el prompt del curator: lista explícita (fallos del entorno, "X no funciona", errores transitorios, narrativas de un uso). Captura el FIX, nunca la queja. | hermes `background_review._MEMORY_REVIEW_PROMPT` | `curator.py` (prompt) | S | nulo |
| 2.3 | **Escritura atómica + lock + drift** de `aprendido.md`: flock + tmp+fsync+rename, `.bak.<ts>` y rehúsa si el fichero cambió por fuera (round-trip check). | hermes `memory_tool._detect_external_drift`, `_write_file` | `curator.py` | S/M | bajo |
| 2.4 | **memory-budget que protege lo humano**: marcar bloques auto-promovidos (`## Promovido (fecha)` + marcador), podar SOLO esos por fecha ascendente hasta el budget; lo humano intocable. | openclaw `memory-budget.compactMemoryForBudget` (budget 10k chars) | `curator.py` | S | bajo |
| 2.5 | **Scoring de promoción de 6 factores + gates**: frequency .24 / relevance .30 / diversity .15 / recency .15 (half-life 14d) / consolidation .10 / conceptual .06; gates minScore 0.75, minRecallCount 3, minUniqueQueries 2. | openclaw `short-term-promotion.rankShortTermPromotionCandidates` | `curator.py` (+`/logs/short_term_recall.json`) | M | medio |
| 2.6 | **Estados decay ACTIVE→STALE(30d)→ARCHIVED(90d)** como función pura sin LLM; nunca borra, archiva (recuperable); reactiva si vuelve el recall. Depende de 2.1. | hermes `curator.apply_automatic_transitions` | `curator.py`, esquema `events.db` | M | medio |
| 2.7 | **Límite que FUERZA consolidación inline**: al añadir un hecho, si se pasa el cap, fusiona en el momento (no espera a la diaria). | hermes `memory_tool.add()` | `curator.py`, `tools/memoria.py` | S | bajo |
| 2.8 | **Fencing anti-inyección**: envolver la memoria inyectada en `<memoria>…</memoria>` con nota "datos, no instrucciones" + scan de patrones al escribir. Relevante por ser voz (entrada menos controlada). | hermes `memory_manager.build_memory_context_block`, `_scan_memory_content` | ensamblado de prompt, `curator.py` | S | bajo |

---

## BLOQUE 3 · Proactividad más barata y potente — 🟠

| # | Tarea | Origen | Archivos | Esf | Riesgo |
|---|-------|--------|----------|:---:|:------:|
| 3.1 | **Heartbeat aislado + lightContext + `HEARTBEAT_OK` formal + tasks por intervalo**: brain_review en sesión fresca con solo un `HEARTBEAT.md` (de ~100K a ~2-5K tokens/run); bloques `tasks:` con su `interval`; si ninguna vence → skip SIN llamar al LLM; `ackMaxChars=300`. | openclaw `heartbeat.md`, `heartbeat-filter.ts` | `proactive.py`, nuevo `HEARTBEAT.md` | M | bajo |
| 3.2 | **Cron en lenguaje natural + SCRIPT-INJECTION + `[SILENT]` + wake-gate**: `parse_schedule` ("every 30m", cron); un script precomputa, su stdout se inyecta como contexto y el LLM solo razona; `{"wakeAgent":false}` salta el LLM entero; `[SILENT]` suprime delivery. Script sandbox (path traversal, timeout, redacción de secretos). | hermes `cron/jobs.py`, `scheduler.py` | nuevo `cron.py`, `/opt/jarvis/scripts/`, cuelga del Heartbeat | M | medio (sandbox) |
| 3.3 | **Monitor de urgencia** (`classify_items`): fetch→LLM barato puntúa 0-10 contra criterios NL→solo lo ≥umbral; vacío→`[SILENT]`. | hermes `cron/scripts/classify_items.py` | nuevo `scripts/classify_items.py` | S | bajo |
| 3.4 | **Store unificado de sugerencias con `job_spec` ejecutable + dedup latcheado + cap 5**: evolucionar `propuestas.json`; aceptar = crear el cron job directamente (no segundo motor). Conecta auto-mejora (task #15) con cron. | hermes `cron/suggestions.py`, `suggestion_catalog.py` | `curator.py`, panel, `cron.py` | M | bajo |

---

## BLOQUE 4 · Calidad del agente (texto/voz) — 🟠

| # | Tarea | Origen | Archivos | Esf | Riesgo |
|---|-------|--------|----------|:---:|:------:|
| 4.1 | **Prompt-cache estable-arriba/volátil-abajo + timestamp fecha-only**: quitar la hora:minuto del system (romper el prefix-cache cada turno); franja "mañana/tarde/noche" o inyectar la hora en el `user`, no en el system. Ganancia directa de coste (el HUD ya mide `cached_tokens`). | hermes `system_prompt.py`, openclaw `system-prompt.md` | `sysprompt.py`, `telegram_agent._momento` | S | bajo |
| 4.2 | **Budget de outputs grandes de tools**: truncar+preview los tool-results (web_read/investigar) antes de meterlos al contexto del siguiente turno. | hermes `tool_result_storage.maybe_persist`, `budget_config` | nuevo `tools/result_budget.py`, `telegram_agent._think` | S | bajo |
| 4.3 | **Clasificador de errores LLM accionable**: `FailoverReason` (rate_limit/context_overflow/billing/content_policy/…) con hints (`retryable`/`should_compress`/`should_fallback`); reintentos con backoff; comprimir `_hist` ante overflow; mensaje específico en vez del genérico. | hermes `error_classifier.classify_api_error` | nuevo `llm_errors.py`, `telegram_agent._chat`, `proactive._llm`, `curator._llm` | M | medio |
| 4.4 | **Tool `todo`** (planificación multi-paso): `TodoStore` en memoria por sesión; guía de conducta en el schema; sobrevive al recorte de `_hist`. | hermes `tools/todo_tool.py` | nuevo `tools/todo.py`, `registry.py`, `tools.yaml` | S/M | bajo |
| 4.5 | **Tool `clarify`** (preguntar a media tarea): en Telegram, no-bloqueante (corta el bucle, manda la pregunta, el siguiente mensaje es la respuesta). En voz, más complejo (dejar para después). | hermes `clarify_tool.py`, `clarify_gateway.py` | nuevo `tools/clarify.py`, `telegram_agent` | M | medio |

---

## BLOQUE 5 · Observabilidad — ⚪ (al final)

| # | Tarea | Origen | Archivos | Esf | Riesgo |
|---|-------|--------|----------|:---:|:------:|
| 5.1 | **Timeline JSONL + flags por env**: `emit(subsystem, span, ms, **meta)` → línea JSON (envelope `jarvis.diag.v1`) a `/logs/timeline.jsonl`; gating `JARVIS_DIAGNOSTICS=stt,llm.*`. Instrumentar el Observer de Pipecat (wake→STT→LLM→TTS). | openclaw `diagnostics.md`, `flags.md` | nuevo `diagnostics.py`, `voice_state.py` | S/M | bajo |
| 5.2 | **Export Prometheus** `/metrics` con buckets ya calibrados para latencias de voz + guardas de cardinalidad. Solo si quieres Grafana. | openclaw `diagnostics-prometheus/service.ts` | `diagnostics.py`, panel | M | bajo |

---

## DESCARTADO (sobreingeniería para Jarvis)
- **ACP adapter** (Agent Client Protocol): es para pilotar el agente DESDE un editor (Zed) por stdio; Jarvis es voz-first sobre HTTP, un solo cliente. ~2000 LOC de complejidad accidental. *Robar solo el concepto* `allow_once/allow_session/allow_always` para `encargar` (ver 1.5).
- **`prompt_caching.py`** de Hermes: `cache_control` es API nativa Anthropic; GLM-5/litellm usa prefix-cache automático (cubierto por 4.1).
- **Re-entrada de delegación async como turno nuevo**: Jarvis ya locuta el resultado por `/event/say`; solo valdría si quieres que el LLM ENCADENE sobre el resultado.

---

## CAMINO CRÍTICO sugerido para UNA sesión larga
1. **Bloque 1 completo (1.1→1.3)** — cerrar el agujero de seguridad del sudo. Es lo responsable.
2. **2.1 + 2.2 + 2.3 + 2.4** — memoria barata y de alto valor (recall, taxonomía, atomicidad, budget humano-safe).
3. **4.1** — el ahorro de prompt-cache (cambio pequeño, beneficio inmediato).

Eso es una sesión coherente y entregable. El resto queda como backlog secuenciado arriba.
