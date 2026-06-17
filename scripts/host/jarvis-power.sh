#!/usr/bin/env bash
# jarvis-power.sh — reposo de recursos del HUD de Jarvis.
# Apaga/enciende la pantalla del kiosko (cage + Chromium) bajo demanda, para no
# gastar recursos cuando no se usa. Se invoca:  sudo /usr/local/bin/jarvis-power.sh {sleep|wake}
# Corre como root (vía sudoers NOPASSWD acotado a este script). Idempotente.
set -u
LOG=/srv/jarvis/logs/power.log
KIOSK=jarvis-kiosk.service
KTIMER=jarvis-kiosk-restart.timer
FB=/sys/class/graphics/fb0/blank

log() { echo "$(date '+%F %T') $*" >> "$LOG" 2>/dev/null || true; }

case "${1:-}" in
  sleep)
    systemctl stop "$KTIMER" 2>/dev/null || true   # que el reinicio nocturno no reencienda
    systemctl stop "$KIOSK"  2>/dev/null || true   # mata Chromium -> libera KMS y CPU
    # cage tarda ~1-2s en soltar el master DRM y el fbcon reajusta blank a 1;
    # reafirmamos FB_BLANK_POWERDOWN varias veces para que el monitor entre en standby.
    for _ in 1 2 3 4; do
      sleep 1
      echo 4 > "$FB" 2>/dev/null || true           # FB_BLANK_POWERDOWN -> monitor a standby
    done
    log "sleep: kiosk parado, pantalla a standby (dpms=$(cat /sys/class/drm/card1-HDMI-A-3/dpms 2>/dev/null))"
    echo "ok sleep"
    ;;
  wake)
    echo 0 > "$FB" 2>/dev/null || true             # desblanquea la consola
    systemctl start "$KIOSK"  2>/dev/null || true  # HUD de vuelta
    systemctl start "$KTIMER" 2>/dev/null || true
    log "wake: pantalla y kiosk restaurados"
    echo "ok wake"
    ;;
  *)
    echo "uso: $0 {sleep|wake}" >&2
    exit 2
    ;;
esac
