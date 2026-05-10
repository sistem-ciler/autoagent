#!/usr/bin/env bash
# deploy.sh — rolling update for SRV-HTZNR-EU-SWS
# Builds locally (images are not pushed to any registry).
# Usage: ./scripts/deploy.sh [service]
# Example: ./scripts/deploy.sh autoagent

set -euo pipefail

SERVICE=${1:-all}

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

deploy_service() {
  local svc=$1
  log "Building ${svc}"
  docker compose build "${svc}"

  log "Rolling update: ${svc}"
  docker compose up -d --no-deps "${svc}"

  log "Waiting for ${svc} healthcheck (up to 60s)..."
  for i in $(seq 1 30); do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$(docker compose ps -q ${svc} 2>/dev/null)" 2>/dev/null || echo "starting")
    [ "$STATUS" = "healthy" ] && { log "${svc} is healthy."; return 0; }
    [ "$STATUS" = "none" ]    && { log "${svc} is up (no healthcheck)."; return 0; }
    sleep 2
  done
  log "WARNING: ${svc} did not become healthy in 60s — check: docker compose logs ${svc}"
}

if [ "$SERVICE" = "all" ]; then
  for s in autoagent autoagent-worker; do
    deploy_service "$s"
  done
else
  deploy_service "$SERVICE"
fi

log "Deploy complete."
docker image prune -f
