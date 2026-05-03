#!/usr/bin/env bash
# deploy.sh — zero-downtime rolling update for SRV-HTZNR-EU-SWS
# Usage: ./scripts/deploy.sh [service] [image_tag]
# Example: ./scripts/deploy.sh autoagent abc1234

set -euo pipefail

SERVICE=${1:-all}
TAG=${2:-latest}

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

deploy_service() {
  local svc=$1
  log "Pulling ghcr.io/sistem-ciler/${svc}:${TAG}"
  docker compose pull "${svc}"

  log "Rolling update: ${svc}"
  docker compose up -d --no-deps "${svc}"

  log "Waiting for ${svc} healthcheck..."
  for i in $(seq 1 30); do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$(docker compose ps -q ${svc})" 2>/dev/null || echo starting)
    [ "$STATUS" = "healthy" ] && { log "${svc} healthy."; return 0; }
    sleep 2
  done
  log "ERROR: ${svc} did not become healthy in 60s"; exit 1
}

if [ "$SERVICE" = "all" ]; then
  for s in autoagent cua trend-radar synapse; do
    deploy_service "$s"
  done
else
  deploy_service "$SERVICE"
fi

log "Deploy complete. Pruning old images."
docker image prune -f
