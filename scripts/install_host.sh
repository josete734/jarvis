#!/usr/bin/env bash
# Host preparation for Ubuntu Server 24.04 on the M70q (PLAN_FINAL §5.0).
# Idempotent-ish: safe to re-run. Run as: sudo bash scripts/install_host.sh
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo"; exit 1; }
REAL_USER="${SUDO_USER:-$USER}"

echo "==> Packages"
apt-get update
apt-get install -y git curl htop sox espeak-ng alsa-utils v4l-utils \
    zram-tools cpufrequtils ufw fail2ban unattended-upgrades restic unzip

echo "==> zram (50%, zstd) + 4 GB safety swapfile on NVMe"
printf 'ALGO=zstd\nPERCENT=50\n' > /etc/default/zramswap
systemctl restart zramswap || true
if [ ! -f /swapfile ]; then
    fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
fi
grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
sysctl -w vm.swappiness=10
grep -q 'vm.swappiness' /etc/sysctl.d/99-jarvis.conf 2>/dev/null || \
    echo 'vm.swappiness=10' > /etc/sysctl.d/99-jarvis.conf

echo "==> CPU governor: performance (35W TDP — low energy cost)"
echo 'GOVERNOR="performance"' > /etc/default/cpufrequtils
systemctl restart cpufrequtils || true

echo "==> Docker"
if ! command -v docker >/dev/null; then
    curl -fsSL https://get.docker.com | sh
fi
for grp in docker audio video render; do
    if getent group "$grp" >/dev/null; then
        usermod -aG "$grp" "$REAL_USER"
    else
        echo "NOTE: group '$grp' not found — skipped (see render note below)"
    fi
done

echo "==> Firewall + SSH hardening + fail2ban"
ufw default deny incoming
ufw allow OpenSSH
ufw --force enable
systemctl enable --now fail2ban
echo "NOTE: set 'PasswordAuthentication no' in /etc/ssh/sshd_config AFTER"
echo "      confirming your SSH key works, then: systemctl restart ssh"

echo "==> Unattended security upgrades"
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "==> Tailscale"
if ! command -v tailscale >/dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sh
fi
echo "NOTE: run 'sudo tailscale up' interactively if not joined yet."

echo "==> Directories (models on NVMe, data on SATA, backups on USB)"
mkdir -p /var/lib/jarvis/models
mkdir -p /srv/jarvis/{chroma,mem0,postgres,n8n,logs,faces}
mkdir -p /mnt/backup
chown -R "$REAL_USER" /var/lib/jarvis /srv/jarvis
echo "NOTE: mount the SATA SSD on /srv/jarvis and the USB disk on /mnt/backup"
echo "      (fstab by LABEL/UUID, with 'nofail' for the USB)."

echo "==> render group GID (set RENDER_GID in .env):"
getent group render || echo "render group not found — check intel drivers"

echo "==> Host scripts, units y sudoers (capa de acciones / voz-off / HUD / backup)"
HOST_DIR="$(cd "$(dirname "$0")/host" && pwd)"
install -o root -g root -m 0755 "$HOST_DIR/jarvis-research.py"  /usr/local/bin/jarvis-research.py
install -o root -g root -m 0755 "$HOST_DIR/jarvis-power.sh"     /usr/local/bin/jarvis-power.sh
install -o root -g root -m 0755 "$HOST_DIR/jarvis-cmd-guard.py" /usr/local/bin/jarvis-cmd-guard.py
install -o root -g root -m 0440 "$HOST_DIR/jarvis-actions.sudoers" /etc/sudoers.d/jarvis-actions
visudo -cf /etc/sudoers.d/jarvis-actions || { echo "sudoers inválido"; exit 1; }
for unit in jarvis-research.service jarvis-kiosk.service jarvis-kiosk-restart.service \
            jarvis-kiosk-restart.timer jarvis-backup.service jarvis-backup.timer; do
    install -o root -g root -m 0644 "$HOST_DIR/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable --now jarvis-research.service jarvis-kiosk.service \
    jarvis-kiosk-restart.timer jarvis-backup.timer
echo "NOTE: el backup necesita el disco USB montado en /mnt/backup y 'restic init' (ver scripts/backup.sh)."

echo "Done. Re-login (or 'newgrp docker') for group changes to apply."
