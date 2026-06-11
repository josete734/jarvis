# RUNBOOK — operación de Jarvis

## Arranque / parada
```bash
make up | make down | make ps | make logs s=orchestrator
sudo systemctl start|stop jarvis            # vía systemd (producción)
```

## Exponer panel y n8n al tailnet
```bash
sudo tailscale serve --bg --https=443  http://127.0.0.1:8080   # panel
sudo tailscale serve --bg --https=8443 http://127.0.0.1:5678   # n8n
tailscale serve status
```
La identidad del tailnet llega al panel en `Tailscale-User-Login` (allowlist en
`.env: PANEL_ALLOWED_USERS`). **Nunca usar Funnel** (expondría a internet sin
identidad). Verificar sintaxis del CLI si cambia (`tailscale serve --help`).

## Añadir una habilidad nueva (acción n8n)
1. Crear el workflow en n8n partiendo de `n8n/workflows/recordatorio.example.json`
   (webhook + Code de verificación HMAC como PRIMER nodo).
2. Declararla en `config/tools.yaml` (`type: side_effect`, descripción clara,
   parámetros). Las side_effect SIEMPRE pasan por confirmación verbal.
3. `make restart s=orchestrator`.

## Cambiar de modelo LLM (A/B/C)
Editar `config/litellm/config.yaml` → línea `model:` de `jarvis-main` →
`make restart s=litellm`. Métricas del A/B: 20 turnos guionizados a ciegas +
tasa de `tool_use_failed` + coste/turno (logs de litellm).

## Activar parakeet (Fase 2-3)
```bash
# 1. compose: STT_BACKEND=openai en orchestrator
# 2. arrancar el servidor STT:
make parakeet-on
make restart s=orchestrator
```
Verificar puerto/healthcheck de la imagen al adoptar (PLAN_FINAL §13.8).
Rollback: `STT_BACKEND=whisper` + `make parakeet-off`.

## Memoria (Fase 3)
- Activar: `MEM0_ENABLED=true` en compose → restart orchestrator.
- El arranque ejecuta el self-test del prefijo e5 — revisar logs: si dice
  "prefix NOT applied", NO continuar (el retrieval se degradaría en silencio).
- Reflexión manual: `make reflection`. Cuarentena de memorias sospechosas:
  revisar la salida en logs y `persona/perfil_usuario.md`.

## Persona y git
El panel guarda `persona/jarvis.md` pero el commit se hace en el host:
```bash
cd /opt/jarvis && git add persona/ && git commit -m "feat(persona): update"
```

## Caras (Fase 5)
Enrolar: capturar 5-10 fotos frontales, extraer embedding medio y guardarlo:
```bash
docker compose exec vision python3 - <<'EOF'
# TODO(Fase 5): pequeño script de enrolado -> /faces/jose.npy
EOF
```
DND desde el panel (sección Presencia).

## Backups
- Diario 05:00 (timer). Manual: `make backup`.
- **Simulacro de restauración mensual** (ponerlo en el calendario):
  `restic -r /mnt/backup/restic restore latest --target /tmp/restore-test`
  y comprobar que `chroma/` y `postgres-dump.sql` están y abren.

## Troubleshooting
| Síntoma | Causa probable / arreglo |
|---|---|
| El orquestador no ve el micro | grupos `audio` (re-login), `make list-audio`, fijar `AUDIO_INPUT_INDEX` |
| `Permission denied renderD128` en vision | `RENDER_GID` mal en `.env` (`getent group render`) |
| Jarvis se interrumpe a sí mismo | AEC insuficiente → re-ejecutar `scripts/test_aec.sh`; plan B/C (PLAN_FINAL §5.2) |
| n8n no deja hacer login | Acceder por `tailscale serve` (https). Solo si vas por http directo: `N8N_SECURE_COOKIE=false` |
| 403 en SearXNG desde web_search | falta `json` en `search.formats` (config/searxng/settings.yml) |
| Corta al usuario al pensar | smart-turn debe estar activo (default); revisar logs antes de subir `stop_secs` |
| `tool_use_failed` frecuentes | modelo B (gpt-oss): descripciones de tools más explícitas o volver a llama-3.3-70b |
| Panel 403 | falta header de identidad → entrar por la URL de `tailscale serve`, no por IP |
