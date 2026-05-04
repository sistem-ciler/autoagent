# SRV-HTZNR-EU-SWS — Production Stack

Single-host, four-service production stack. Solo-operated. Hetzner Falkenstein (CCX52).
All infra is defined in `docker-compose.yml`; all secrets live in `.env` (never committed).

## Services

| Service | Role | Internal port | External |
|---|---|---|---|
| autoagent | AI Autopilot Agents (FastAPI + Celery) | 8080 | api.hexsec.dev |
| cua | Computer-use sandbox (FastAPI + KVM) | 8443 | cua.hexsec.dev |
| trend-radar | Scraper + X-Studio (Next.js) | 3000 | radar.hexsec.dev |
| synapse | Matrix homeserver (E2EE chat) | 8008 | matrix.hexsec.dev |

## Shared Infrastructure

| Component | Image | Purpose |
|---|---|---|
| postgres:16 | schema-isolated per service | persistent data |
| redis:7 | Celery queue + session cache | queue / cache |
| minio | quay.io/minio/minio | blob store (frames, artefacts) |
| caddy:2 | reverse proxy | auto-TLS, HTTP/3, HSTS |
| prometheus | prom/prometheus | metrics scraping |
| grafana | grafana/grafana | dashboards |
| loki + promtail | grafana/loki | log aggregation |

## Quick Start

```bash
# 1. Copy and fill secrets
cp .env.example .env
$EDITOR .env   # replace all CHANGE_ME_ values

# 2. Bring up shared infra first (postgres must be healthy before apps start)
make up-infra

# 3. Start application services
make up-apps

# 4. Start edge + observability
make up-obs

# 5. Verify all containers healthy
make status
```

## Make Targets

```
make up          # bring up everything
make up-infra    # postgres + redis + minio only
make up-apps     # application services only
make up-obs      # caddy + prometheus + grafana + loki + promtail
make down        # stop everything
make status      # table of container health
make logs        # tail all logs
make logs-svc    # SVC=autoagent make logs-svc  (single service)
make pull        # pull latest images
make deploy      # SVC=autoagent make deploy  (rolling update)
make backup      # pg_dump all schemas → /tmp/
make clean       # prune stopped containers + dangling images
make shell       # SVC=autoagent make shell  (exec sh in container)
```

## Deployment Pipeline

```
git push origin main
      │
      ▼
GitHub Actions (.github/workflows/deploy.yml)
  1. docker build → ghcr.io/sistem-ciler/<service>:<sha>
  2. docker push
  3. POST /webhook  (X-Deploy-Token: HMAC-SHA256)
      │
      ▼
scripts/webhook-server.py  (runs on host, port 9000)
  4. validate HMAC
  5. exec scripts/deploy.sh <service> <sha>
      │
      ▼
scripts/deploy.sh
  6. docker compose pull <service>
  7. docker compose up -d --no-deps <service>
  8. wait for healthcheck
  9. docker image prune
```

### Starting the webhook server

```bash
# One-shot (tmux/screen)
DEPLOY_TOKEN=$(cat /run/secrets/deploy_token) python3 scripts/webhook-server.py

# As a systemd service
sudo cp contrib/webhook-server.service /etc/systemd/system/
sudo systemctl enable --now webhook-server
```

### Manual rollout

```bash
# Single service
./scripts/deploy.sh autoagent latest

# All services
./scripts/deploy.sh all

# Emergency rollback (pin to previous SHA)
docker compose pull autoagent  # pulls :latest
docker compose up -d --no-deps autoagent
```

## Security

- **TLS**: 1.3 only via Caddy. HSTS preload + OCSP stapling.
- **Firewall**: UFW — inbound 22, 80, 443, 8448 only.
- **SSH**: key-only, non-default port. fail2ban with tight jails.
- **Secrets**: `.env` file, mounted read-only. Verified by gitleaks pre-commit.
- **DB isolation**: per-service Postgres roles + databases.
- **Disk**: LUKS full-disk encryption on Hetzner host.
- **Containers**: Docker rootless — no daemon root.
- **Matrix**: E2EE on by default for all rooms.

## Observability

- **Prometheus**: scrapes all services on `/metrics` every 15 s
- **Grafana**: `https://ops.hexsec.dev/grafana/` (admin-only, basic-auth)
- **Loki**: log aggregation via Promtail (Docker container logs)
- **Alerts**: fire to private Matrix room `#ops:hexsec.dev` on this same Synapse

## Backup & Recovery

| What | How | Where | Retention |
|---|---|---|---|
| Postgres schemas | nightly `pg_dump` + `age` encrypt | Hetzner Storage Box via Borg | 90 days |
| Media (Synapse) | rsync nightly | Storage Box | 30 days |
| MinIO blobs | `mc mirror` nightly | Storage Box | 30 days |

**Recovery objective**: <30 min from a fresh CCX52 (Postgres WAL + Borg restore).
Monthly restore drill: boot clean VPS → restore → verify all healthchecks green.
