# Historial del homelab anterior (calahierbas.casa)

> Referencia capturada el **2026-06-12** del Cloudflare Tunnel "CASA" (id `09610c58-3aca-4781-bf72-5d17fdbb19d1`, ya muerto) antes de limpiar sus 22 registros DNS. El servidor que lo servía (NVMe/SATA del homelab viejo) se reinstaló. **No es una tarea activa**: solo un mapa por si en el futuro se redespliega algún servicio.

Topología antigua: `cloudflared` corría en una máquina y enrutaba a servicios locales (`127.0.0.1` / `localhost`) o a otra caja de la LAN en `192.168.0.100`.

## Subdominios → servicio:puerto (ingress del tunnel)

| Subdominio | Destino | Servicio probable |
|------------|---------|-------------------|
| `calahierbas.casa` (raíz) | http://127.0.0.1:7575 | Homarr/dashboard (7575 = Homarr) |
| `glance.calahierbas.casa` | http://192.168.0.100:61208 | Glances (métricas) |
| `ha.calahierbas.casa` | http://127.0.0.1:8123 | Home Assistant |
| `n8n.calahierbas.casa` | http://192.168.0.100:5678 | n8n (automatización) |
| `plex.calahierbas.casa` | http://192.168.0.100:32400 | Plex Media Server |
| `sonarr.calahierbas.casa` | http://192.168.0.100:8989 | Sonarr (series) |
| `radarr.calahierbas.casa` | http://192.168.0.100:7878 | Radarr (películas) |
| `prowlarr.calahierbas.casa` | http://192.168.0.100:9696 | Prowlarr (indexers) |
| `bazarr.calahierbas.casa` | http://192.168.0.100:6767 | Bazarr (subtítulos) |
| `qbittorrent.calahierbas.casa` | http://192.168.0.100:8070 | qBittorrent |
| `beszel.calahierbas.casa` | http://127.0.0.1:8090 | Beszel (monitor) |
| `vault.calahierbas.casa` | http://localhost:8200 | Vaultwarden/Vault (8200) |
| `archivos.calahierbas.casa` | https://192.168.0.100:1100 | Gestor de archivos (HTTPS) |
| `files.calahierbas.casa` | http://127.0.0.1:8080 | Gestor de archivos / web |
| `video.calahierbas.casa` | http://192.168.0.100:3100 | Servicio de vídeo |
| `viniplay.calahierbas.casa` | http://192.168.0.100:8998 | ViniPlay (IPTV?) |
| `iptv.calahierbas.casa` | http://localhost:7095 | IPTV |
| `neo.calahierbas.casa` | http://192.168.0.100:3000 y https://192.168.0.100:18789 | "neo" (2 puertos) |
| `spot.calahierbas.casa` | http://localhost:8800 | Spot (¿spotify-dl?) |
| `tareas.calahierbas.casa` | http://localhost:3456 | Gestor de tareas |
| `ssh.calahierbas.casa` | ssh://192.168.0.100 | SSH por el tunnel |

## Notas para un futuro redespliegue
- La mayoría de estos servicios vivían en `/home/jose/docker` (~650 GB, formateado) y `/opt/stacks`.
- Hoy el tunnel activo es **`calahierbas`** (id `cdf1d4d3-...`) sirviendo solo `jarvis.calahierbas.casa` → panel.
- Para revivir uno: levantar el servicio en este server, añadir su regla al ingress del tunnel (API `cfd_tunnel/.../configurations`), crear el DNS CNAME `<sub> → <tunnelid>.cfargotunnel.com` (proxied) y, si es sensible, una app de Cloudflare Access.
