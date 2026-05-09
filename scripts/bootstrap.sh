#!/usr/bin/env bash
# ============================================================
#  godoman.net — SRV-HTZNR-EU-SWS bootstrap
#  Installs: claude-code CLI, ruflo MCP, docker stack
#  Usage: curl -fsSL https://raw.githubusercontent.com/sistem-ciler/autoagent/claude/build-money-machine-cWtcY/scripts/bootstrap.sh | bash
# ============================================================
set -euo pipefail

DOMAIN="godoman.net"
ACME_EMAIL="ops@godoman.net"
REPO="https://github.com/sistem-ciler/autoagent.git"
BRANCH="claude/build-money-machine-cWtcY"
WORKDIR="/srv/godoman"

red()   { printf '\e[31m%s\e[0m\n' "$*"; }
green() { printf '\e[32m%s\e[0m\n' "$*"; }
bold()  { printf '\e[1m%s\e[0m\n'  "$*"; }

bold "══════════════════════════════════════════════════"
bold "  godoman.net — production bootstrap"
bold "  host: $(hostname) · $(date -u +%Y-%m-%dT%H:%M:%SZ)"
bold "══════════════════════════════════════════════════"

# ── 1. System deps ────────────────────────────────────────
green "[1/9] system packages"
apt-get update -qq
apt-get install -y --no-install-recommends \
    ca-certificates curl git wget gnupg lsb-release \
    apt-transport-https software-properties-common \
    build-essential jq unzip

# ── 2. Docker ─────────────────────────────────────────────
green "[2/9] docker"
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
    green "  docker installed"
else
    green "  docker already present — $(docker --version)"
fi

# ── 3. Node 22 ────────────────────────────────────────────
green "[3/9] node 22"
if ! node --version 2>/dev/null | grep -q 'v22'; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y nodejs
    green "  node $(node --version) installed"
else
    green "  node $(node --version) already present"
fi

# ── 4. Bun ────────────────────────────────────────────────
green "[4/9] bun"
if ! command -v bun &>/dev/null; then
    curl -fsSL https://bun.sh/install | bash
    export PATH="$HOME/.bun/bin:$PATH"
    echo 'export PATH="$HOME/.bun/bin:$PATH"' >> ~/.bashrc
    green "  bun $(bun --version) installed"
else
    green "  bun $(bun --version) already present"
fi

# ── 5. Claude Code CLI ────────────────────────────────────
green "[5/9] claude-code CLI"
if ! command -v claude &>/dev/null; then
    npm install -g @anthropic-ai/claude-code
    green "  claude-code installed"
else
    green "  claude-code already present"
fi

# Clone sistem-ciler/claude-code source (reference / customisation layer)
mkdir -p /opt/sistem-ciler
if [ ! -d /opt/sistem-ciler/claude-code ]; then
    git clone https://github.com/sistem-ciler/claude-code /opt/sistem-ciler/claude-code
    green "  sistem-ciler/claude-code cloned → /opt/sistem-ciler/claude-code"
fi

# ── 6. Ruflo ──────────────────────────────────────────────
green "[6/9] ruflo multi-agent orchestration"
if ! command -v ruflo &>/dev/null 2>&1; then
    # try CDN installer first, fall back to npx
    curl -fsSL https://cdn.jsdelivr.net/gh/ruvnet/ruflo@main/scripts/install.sh | bash 2>/dev/null \
        || npx --yes ruflo@latest init wizard --yes 2>/dev/null \
        || true
fi

# Clone sistem-ciler/ruflo (customised fork)
if [ ! -d /opt/sistem-ciler/ruflo ]; then
    git clone https://github.com/sistem-ciler/ruflo /opt/sistem-ciler/ruflo
    green "  sistem-ciler/ruflo cloned → /opt/sistem-ciler/ruflo"
fi

# Install ruflo deps from local fork
cd /opt/sistem-ciler/ruflo
bun install --frozen-lockfile 2>/dev/null || npm install 2>/dev/null || true

# Register ruflo MCP server with Claude Code
claude mcp add ruflo -- npx ruflo@latest mcp start 2>/dev/null || true
green "  ruflo MCP registered with claude-code"

# Systemd unit for ruflo MCP daemon
cat > /etc/systemd/system/ruflo-mcp.service << 'UNIT'
[Unit]
Description=Ruflo MCP server
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/npx ruflo@latest mcp start
Restart=on-failure
RestartSec=5
EnvironmentFile=/srv/godoman/autoagent/.env

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable ruflo-mcp
green "  ruflo-mcp systemd unit enabled"

# ── 7. Clone / update orchestration stack ─────────────────
green "[7/9] orchestration stack"
mkdir -p "$WORKDIR"
if [ ! -d "$WORKDIR/autoagent" ]; then
    git clone -b "$BRANCH" "$REPO" "$WORKDIR/autoagent"
    green "  autoagent repo cloned"
else
    cd "$WORKDIR/autoagent" && git pull origin "$BRANCH"
    green "  autoagent repo updated"
fi

# ── 8. Environment ────────────────────────────────────────
green "[8/9] .env setup"
cd "$WORKDIR/autoagent"
if [ ! -f .env ]; then
    cp .env.example .env
    # Patch domain references
    sed -i "s/DOMAIN=.*/DOMAIN=${DOMAIN}/"          .env
    sed -i "s/ACME_EMAIL=.*/ACME_EMAIL=${ACME_EMAIL}/" .env
    sed -i "s|NEXTAUTH_URL=.*|NEXTAUTH_URL=https://radar.${DOMAIN}|" .env
    sed -i "s|ADMIN_EMAILS=.*|ADMIN_EMAILS=ops@${DOMAIN}|"           .env
    red ""
    red "  ⚠️  .env created with placeholder secrets."
    red "  Edit NOW before starting the stack:"
    red "  nano $WORKDIR/autoagent/.env"
    red ""
else
    green "  .env already exists — skipping"
fi

# ── 9. Firewall ───────────────────────────────────────────
green "[9/9] firewall (ufw)"
if command -v ufw &>/dev/null; then
    ufw --force enable
    ufw allow 22/tcp   # SSH
    ufw allow 80/tcp   # HTTP (Caddy + Let's Encrypt)
    ufw allow 443/tcp  # HTTPS
    ufw allow 443/udp  # HTTP/3
    ufw allow 8448/tcp # Matrix federation
    green "  ufw rules applied"
fi

# ── Done ──────────────────────────────────────────────────
bold ""
bold "══════════════════════════════════════════════════"
bold "  Bootstrap complete ✓"
bold ""
bold "  NEXT STEPS:"
bold ""
bold "  1. Fill in secrets:"
bold "     nano $WORKDIR/autoagent/.env"
bold ""
bold "  2. Start the stack:"
bold "     cd $WORKDIR/autoagent && docker compose up -d"
bold ""
bold "  3. Start ruflo MCP daemon:"
bold "     systemctl start ruflo-mcp"
bold ""
bold "  4. Point DNS A records → 188.245.210.10:"
bold "     @             godoman.net"
bold "     api           api.godoman.net"
bold "     radar         radar.godoman.net"
bold "     matrix        matrix.godoman.net  (DNS-only, no proxy)"
bold "     cua           cua.godoman.net"
bold "     ops           ops.godoman.net"
bold ""
bold "  Stack URLs (after DNS propagates):"
bold "     https://radar.godoman.net   — trend intelligence"
bold "     https://api.godoman.net     — agent API"
bold "     https://ops.godoman.net     — grafana + prometheus"
bold "     https://matrix.godoman.net  — Matrix / synapse"
bold "══════════════════════════════════════════════════"
