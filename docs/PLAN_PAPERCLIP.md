# Plan de robos de Paperclip → Jarvis

Análisis a fondo (código real) de [paperclipai/paperclip](https://github.com/paperclipai/paperclip)
— una plataforma de orquestación de EQUIPOS de agentes ("si OpenClaw es un empleado,
Paperclip es la empresa"). El 90% es maquinaria multi-tenant que Jarvis (mayordomo
mono-usuario) no necesita; aquí queda lo **robable de verdad**, priorizado.

> **Estado:** ✅ Sprint 1 (gobernanza del Curator) IMPLEMENTADO — ver abajo. Fases 2-4 pendientes.

---

## ✅ Sprint 1 — Tubería de gobernanza del Curator (HECHO)

La auto-mejora del perfil pasó de "append ciego sin deshacer, solo en el panel" a un ciclo robusto:
**aprobación → revisión reversible → audit**, con entrega por **Telegram con botones**.

- **Audit log inmutable** (`activity_log.ts`): tabla `audit_log` en events.db con triggers anti-UPDATE/DELETE. Helper en `orchestrator/audit.py` (futuro) y `panel/main.py:_audit` (en uso). Acciones: `proposal.approved|rejected|revision_requested`, `profile.config_rolled_back`.
- **Perfil revisionado + rollback** (`agent_config_revisions.ts`): `/logs/config_revisions.json` con snapshot before/after; botón "Deshacer" en el panel (`/propuesta/rollback/{rev_id}`).
- **Cola de aprobaciones genérica** (`approvals.ts`): estados `pendiente/aprobada/rechazada/revision_requested/superseded`; función única `_apply_decision()` compartida por el panel y Telegram.
- **Telegram con botones** (Aprobar/Rechazar/**Reformular**): el Curator empuja cada propuesta con `inline_keyboard`; `telegram_agent._on_callback` aplica vía el endpoint interno del panel `POST /api/propuesta/decision` (auth `EVENTS_SECRET`, porque el orquestador tiene `/persona` en solo-lectura). "Reformular" → el Curator reescribe la propuesta de otra forma (`rework_requested`).

---

## Fase 2 — Endurecer la delegación (`encargar`)

- **Secretos *scoped* por run** (`server/src/services/secrets.ts`): partir el `.env` monolítico; `investigar` recibe menos secretos que `encargar`; resolver solo lo "bound" por run, con audit de acceso. **Valor MUY ALTO** (mayor reducción de superficie de ataque; hoy un prompt-injection en `investigar` podría exfiltrar cualquier secreto del `.env`).
- **Worktree-por-tarea + close-readiness hablado** (`server/src/services/execution-workspaces.ts:inspectGitCloseReadiness`): `encargar` de archivos en un `git worktree`; al terminar, resumen "cambié N ficheros, M commits por delante, ¿integro/reviso/descarto?". Aislamiento + preview + rollback con solo `git`. **Valor ALTO.**
- **Run JWT efímero** (`server/src/agent-auth-jwt.ts`): credencial HS256 TTL ~15 min atada al run, inyectada al subproceso `claude`; el guardián la verifica. **Valor MEDIO-ALTO** (~30 líneas en Python).
- **Capabilities declarativas fail-closed** en el guardián (`plugin-capability-validator.ts`): mapa `tool → capability`; `investigar → {web, fs.read}`, `encargar → {fs.write, bash}`; herramienta no mapeada = denegada. **Valor MEDIO.**
- **Invocación `claude --output-format stream-json`** + `--resume` + **prompt por stdin** (`adapters/claude-local/src/server/execute.ts`): capturar coste/tokens/sesión por orden de voz, memoria de sesión entre encargos, y que el prompt deje de salir en `ps aux`. **Valor ALTO.**

## Fase 3 — Memoria y tareas

- **Memoria PARA de 3 capas** sobre el FTS5 existente (`skills/para-memory-files`): daily notes + entidades `summary.md`/`items.yaml` + `aprendido.md`, con **supersede-no-borres** y recencia **Hot/Warm/Cold**. Ya hay motor (recall/decay); falta la estructura. **Valor ALTO.**
- **`task_sessions` (clave única + `state_json`) → reanudar entre latidos** + **reencolar runs al arrancar** (`server/src/services/heartbeat.ts`): que una tarea de cron continúe lo que el latido anterior empezó, en vez de arrancar de cero. **Valor ALTO.**
- **Continuation summary por tarea** (`server/src/services/issue-continuation-summary.ts`): resumen destilado y persistido que el siguiente run lee; detecta "esperando aprobación". **Valor ALTO** para tareas multi-sesión.
- **Goal ancestry** (`packages/db/src/schema/goals.ts` self-ref + CTE recursivo → prompt): toda tarea ve siempre el "por qué". Jarvis lo hace **mejor** que Paperclip (que no inyecta la cadena). **Valor MEDIO.**

## Fase 4 — Skills y extras

- **Skills en markdown** (frontmatter `name`+`description` + carga perezosa) — el patrón de OpenClaw/Claude Code (`docs/guides/agent-developer/writing-a-skill.md`, `packages/skills-catalog/src/frontmatter.ts`). **Valor ALTO.**
- **Hard-stop de presupuesto** (`server/src/services/budgets.ts`): flag global + gate pre-acción + override verbal, como kill-switch anti-runaway. **Valor MEDIO-ALTO.**
- **Work products con `reviewState`** (`issue_work_products.ts`), **inbox-state que resucita con actividad** (`issue_inbox_archives.ts`), **checkout atómico** (`UPDATE...WHERE status='todo' RETURNING`) para idempotencia de cron, **tool-call trace** (`heartbeat_run_events.ts`, `seq` + redacción de secretos). **Valor MEDIO.**

## ❌ No robar (maquinaria multi-tenant)
Org charts, multi-empresa, teams-catalog / skills-catalog con versionado en BD y marketplace (fork/star), `finance_events` (facturación a clientes), tree-holds con doble traza, sandbox k8s, runtime services / dev-servers, reaping de process-groups, `pg_advisory_lock`, materialización de skills en FS.

---

## Dos historias de composición (lo más elegante del análisis)

1. **Ciclo del Curator** (✅ Sprint 1): aprobación (con "reformular") → revisión reversible → audit, en una sola tubería coherente.
2. **Puente Claude Code blindado** (Fase 2): secretos scoped + run JWT + capabilities fail-closed convierten `encargar` de "confío en el prompt + un guardián" en defensa en profundidad real.
