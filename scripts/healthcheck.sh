#!/usr/bin/env bash
# Quick status sweep. Usage: bash scripts/healthcheck.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

echo "==> containers"
docker compose ps --format 'table {{.Name}}\t{{.State}}\t{{.Status}}'

echo
echo "==> in-network probes"
docker compose exec -T orchestrator sh -c '
  for url in http://litellm:4000/health/liveliness http://vision:8089/health http://localhost:8070/health; do
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$url")
    echo "$url -> $code"
  done' 2>/dev/null || echo "orchestrator not running"

echo
echo "==> panel (host)"
curl -s -o /dev/null -w "http://127.0.0.1:8080/health -> %{http_code}\n" --max-time 3 http://127.0.0.1:8080/health

echo
echo "==> disk"
df -h / /var/lib/docker /srv/jarvis /mnt/backup 2>/dev/null | awk 'NR==1 || /\//' || true
