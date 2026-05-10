#!/usr/bin/env bash
# ============================================================
#  godoman.net — SRV-HTZNR-EU-SWS bootstrap
#  Run as: ops (sudo group member)
#  Usage: curl -fsSL https://raw.githubusercontent.com/sistem-ciler/autoagent/claude/build-money-machine-cWtcY/scripts/bootstrap.sh | bash
# ============================================================
set -euo pipefail

DOMAIN="godoman.net"
ACME_EMAIL="ops@godoman.net"
REPO="https://github.com/sistem-ciler/autoagent.git"
BRANCH="claude/build-money-machine-cWtcY"
WORKDIR="/srv/godoman"
USER="${USER:-ops}"

red()   { printf '\e[31m%s\e[0m\n' "$*"; }
green() { printf '\e[32m%s\e[0m\n' "$*"; }
bold()  { printf '\e[1m%s\e[0m\n'  "$*"; }

bold "══════════════════════════════════════════════════"
bold "  godoman.net — production bootstrap"
bold "  user: $USER · host: $(hostname) · $(date -u +%Y-%m-%dT%H:%M:%SZ)"
bold "══════════════════════════════════════════════════"

# ── 1. System deps ────────────────────────────────────────
green "[1/9] system packages"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    ca-certificates curl git wget gnupg lsb-release \
    apt-transport-https software-properties-common \
    build-essential jq unzip

# ── 2. Docker ─────────────────────────────────────────────
green "[2/9] docker"
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sudo sh
    sudo systemctl enable --now docker
    green "  docker installed"
else
    green "  docker already present — $(docker --version)"
fi
# Add ops to docker group so sudo isn\'t needed for docker commands
sudo usermod -aG docker "$USER"
green "  $USER added to docker group (re-login to activate)"

# ── 3. Node 22 ────────────────────────────────────────────
green "[3/9] node 22"
if ! node --version 2>/dev/null | grep -q 'v22'; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt-get install -y nodejs
    green "  node $(node --version) installed"
else
    green "  node $(node --version) already present"
fi

# ── 4. Bun ────────────────────────────────────────────────
green "[4/9] bun"
if ! command -v bun &>/dev/null; then
    curl -fsSL https://bun.sh/install | bash
    export PATH="$HOME/.bun/bin:$PATH"
    echo 'export PATH="$HOME/.bun/bin:$PATH"' >> "$HOME/.bashrc"
    green "  bun $(bun --version) installed"
else
    green "  bun $(bun --version) already present"
fi

# ── 5. Claude Code CLI ────────────────────────────────────
green "[5/9] claude-code CLI"
if ! command -v claude &>/dev/null; then
    sudo npm install -g @anthropic-ai/claude-code
    green "  claude-code installed"
else
    green "  claude-code already present"
fi

# Clone sistem-ciler/claude-code (source reference + customisation base)
sudo mkdir -p /opt/sistem-ciler
sudo chown "$USER:$USER" /opt/sistem-ciler
if [ ! -d /opt/sistem-ciler/claude-code ]; then
    git clone https://github.com/sistem-ciler/claude-code /opt/sistem-ciler/claude-code
    green "  sistem-ciler/claude-code → /opt/sistem-ciler/claude-code"
fi

# ── 6. Ruflo ──────────────────────────────────────────────
green "[6/9] ruflo multi-agent orchestration"
if [ ! -d /opt/sistem-ciler/ruflo ]; then
    git clone https://github.com/sistem-ciler/ruflo /opt/sistem-ciler/ruflo
    green "  sistem-ciler/ruflo → /opt/sistem-ciler/ruflo"
fi
cd /opt/sistem-ciler/ruflo
bun install --frozen-lockfile 2>/dev/null || npm install 2>/dev/null || true

# Install ruflo globally (CDN installer, falls back to npx)
if ! command -v ruflo &>/dev/null 2>&1; then
    curl -fsSL https://cdn.jsdelivr.net/gh/ruvnet/ruflo@main/scripts/install.sh | bash 2>/dev/null \
        || sudo npx --yes ruflo@latest init wizard --yes 2>/dev/null \
        || true
fi

# Register ruflo MCP server with Claude Code
claude mcp add ruflo -- npx ruflo@latest mcp start 2>/dev/null || true
green "  ruflo MCP registered with claude-code"

# Systemd unit — runs as ops, not root
sudo tee /etc/systemd/system/ruflo-mcp.service > /dev/null << UNIT
[Unit]
Description=Ruflo MCP server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/opt/sistem-ciler/ruflo
ExecStart=/usr/bin/npx ruflo@latest mcp start
Restart=on-failure
RestartSec=5
EnvironmentFile=$WORKDIR/autoagent/.env

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable ruflo-mcp
green "  ruflo-mcp systemd unit enabled (runs as $USER)"

# ── 7. Orchestration stack ─────────────────────────────────
green "[7/9] orchestration stack"
sudo mkdir -p "$WORKDIR"
sudo chown "$USER:$USER" "$WORKDIR"
if [ ! -d "$WORKDIR/autoagent" ]; then
    git clone -b "$BRANCH" "$REPO" "$WORKDIR/autoagent"
    green "  autoagent repo cloned → $WORKDIR/autoagent"
else
    cd "$WORKDIR/autoagent" && git pull origin "$BRANCH"
    green "  autoagent repo updated"
fi

# ── 8. Environment ────────────────────────────────────────
green "[8/9] .env setup"
cd "$WORKDIR/autoagent"
if [ ! -f .env ]; then
    cp .env.example .env
    sed -i "s/DOMAIN=.*/DOMAIN=${DOMAIN}/"             .env
    sed -i "s/ACME_EMAIL=.*/ACME_EMAIL=${ACME_EMAIL}/" .env
    sed -i "s|NEXTAUTH_URL=.*|NEXTAUTH_URL=https://radar.${DOMAIN}|" .env
    sed -i "s|ADMIN_EMAILS=.*|ADMIN_EMAILS=ops@${DOMAIN}|"           .env
    red ""
    red "  ⚠️  .env created — fill in secrets before starting the stack:"
    red "  nano $WORKDIR/autoagent/.env"
    red ""
else
    green "  .env already exists — skipping"
fi

# ── 9. Firewall ───────────────────────────────────────────
green "[9/9] firewall (ufw)"
if command -v ufw &>/dev/null; then
    sudo ufw --force enable
    sudo ufw allow 22/tcp   # SSH
    sudo ufw allow 80/tcp   # HTTP
    sudo ufw allow 443/tcp  # HTTPS
    sudo ufw allow 443/udp  # HTTP/3
    sudo ufw allow 8448/tcp # Matrix federation
    green "  ufw rules applied"
fi

# ── Done ──────────────────────────────────────────────────
bold ""
bold "══════════════════════════════════════════════════"
bold "  Bootstrap complete ✓"
bold ""
bold "  NOTE: log out and back in (or run: newgrp docker)"
bold "  so your docker group membership takes effect."
bold ""
bold "  NEXT STEPS:"
bold ""
bold "  1. Fill in secrets:"
bold "     nano $WORKDIR/autoagent/.env"
bold ""
bold "  2. Start the full stack:"
bold "     cd $WORKDIR/autoagent && docker compose up -d"
bold ""
bold "  3. Start ruflo MCP daemon:"
bold "     sudo systemctl start ruflo-mcp"
bold ""
bold "  4. DNS A records → 188.245.210.10 in Cloudflare:"
bold "     @       — godoman.net          (proxied)"
bold "     api     — api.godoman.net      (proxied)"
bold "     radar   — radar.godoman.net    (proxied)"
bold "     ops     — ops.godoman.net      (proxied)"
bold "     cua     — cua.godoman.net      (proxied)"
bold "     matrix  — matrix.godoman.net   (DNS only — no orange cloud)"
bold "══════════════════════════════════════════════════"
