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
# 1. compose: STT_BACKEND=openai en el orchestrator (STT_BASE_URL ya apunta a :5092)
# 2. arrancar el servidor STT (ghcr.io/achetronic/parakeet:0.5.0-int8, puerto 5092):
make parakeet-on
make restart s=orchestrator
```
Apagar: `make parakeet-off` (hace `stop stt-parakeet`; NO uses `--profile ... down` a secas,
tumbaría todo el stack). Rollback: `STT_BACKEND=whisper` + `make parakeet-off`.

## Memoria (Fase 3)
- Activar: `MEM0_ENABLED=true` en compose → restart orchestrator.
- El arranque ejecuta el self-test del prefijo e5 — revisar logs: si dice
  "prefix NOT applied", NO continuar (el retrieval se degradaría en silencio).
- Reflexión manual: `make reflection`. Cuarentena de memorias sospechosas:
  revisar la salida en logs y `persona/perfil_usuario.md`.

## Verificar el log de conversación (user_said / assistant_said)
Tras una conversación de prueba ("hey Jarvis" + pregunta + respuesta):
```bash
sqlite3 /srv/jarvis/logs/events.db \
  "SELECT datetime(ts,'unixepoch','localtime'), kind, payload \
   FROM events WHERE kind IN ('user_said','assistant_said') ORDER BY ts DESC LIMIT 10;"
```
Debe haber una fila `user_said` por transcripción y una `assistant_said` por turno (si hubo
barge-in, lleva `"interrupted": true`). La reflexión nocturna usa una ventana de 24 h, así que
ya no dirá "No conversations today" en cuanto existan estas filas.

## Persona y git
El panel guarda `persona/jarvis.md` pero el commit se hace en el host:
```bash
cd /opt/jarvis && git add persona/ && git commit -m "feat(persona): update"
```

## Caras (Fase 5)
Enrolar una identidad (5-10 muestras frontales con buena luz; cada imagen con UNA cara):
```bash
docker compose stop vision                   # la cámara es de consumidor único (V4L2)
docker compose run --rm vision python3 enroll_face.py --name jose --from-camera 8
#  o desde fotos montadas:  ... enroll_face.py --name jose --from-dir /faces/samples
docker compose start vision                  # recarga las plantillas de /faces/
```
El script avisa si la similitud entre muestras baja de 0,5 (muestras inconsistentes; repetir).
Borrar una identidad: eliminar `/faces/<name>.npy` y reiniciar vision. DND desde el panel.

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
