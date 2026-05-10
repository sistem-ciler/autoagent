#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/srv/godoman/autoagent"

cd "$REPO_DIR"

echo "==> Pulling latest code..."
git pull origin main

echo "==> Building images..."
docker compose build autoagent autoagent-worker autoagent-beat

echo "==> Restarting services..."
docker compose up -d autoagent autoagent-worker autoagent-beat

echo "==> Deploy complete."
