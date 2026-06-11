---
name: deploy-operate
description: >-
  Úsala para arrancar, parar, reconstruir, ver logs, comprobar salud o exponer
  los servicios de Jarvis (docker compose, Makefile, systemd, tailscale serve).
  Cuando José diga "arranca", "levanta", "reinicia", "logs", "está caído", etc.
---

# Operar Jarvis

## Mapa de servicios (docker-compose.yml)
`litellm` (proxy LLM :4000) · `chroma` (vector store) · `searxng` (buscador) ·
`postgres` + `n8n` (acciones :5678) · `orchestrator` (voz, cerebro, tools) ·
`vision` (presencia + /frame) · `socket-proxy` + `panel` (:8080) ·
`reflection` (job nocturno, perfil `jobs`) · `stt-parakeet` (perfil `stt-parakeet`, Fase 2-3).

Datos: modelos en `/var/lib/jarvis/models` (NVMe); estado en `/srv/jarvis/*` (SATA);
backups en `/mnt/backup` (USB).

## Comandos
```bash
make build                 # construir imágenes
make up                    # arrancar (docker compose up -d)
make ps                    # estado
make logs s=orchestrator   # seguir logs de un servicio
make restart s=litellm     # reiniciar uno
make down                  # parar todo
make health                # barrido de healthchecks (scripts/healthcheck.sh)
make list-audio            # índices de micro/altavoz (PyAudio)
```

## Exponer al tailnet (panel y n8n; nunca a internet)
```bash
sudo tailscale serve --bg --https=443  http://127.0.0.1:8080   # panel
sudo tailscale serve --bg --https=8443 http://127.0.0.1:5678   # n8n
tailscale serve status
```
Verifica la sintaxis del CLI si cambió (`tailscale serve --help`). El panel exige
el header `Tailscale-User-Login` ∈ `PANEL_ALLOWED_USERS` del `.env`.

## Producción (systemd)
```bash
sudo cp systemd/* /etc/systemd/system/ && sudo systemctl daemon-reload
sudo systemctl enable --now jarvis.service jarvis-reflection.timer jarvis-backup.timer
systemctl status jarvis        # estado
journalctl -u jarvis -f        # logs del arranque
```
`jarvis.service` depende de `tailscaled.service` (el bind a 127.0.0.1 + serve lo exige).

## Orden de arranque y dependencias
litellm/chroma/searxng/n8n primero; orchestrator depende de ellos. Si el
orchestrator falla, mira primero que litellm responde: `make health`.

## Reglas
- Activar funciones por fase es vía variables de entorno del compose
  (`MEM0_ENABLED`, `STT_BACKEND`, `DISABLE_PRESENCE`) — ver skill `advance-phase`.
- Cambios en `config/tools.yaml` o `persona/` requieren `make restart s=orchestrator` (v1).
- No expongas puertos a `0.0.0.0`: los binds son a `127.0.0.1` y salen por Tailscale.
