#!/usr/bin/env bash
# Lore on an AWS EC2 Ubuntu 24.04 server: Docker, the repo, the graph snapshot, FalkorDB + backend +
# Caddy (automatic HTTPS on <ip-with-dashes>.sslip.io) with docker compose. Safe to run again: it
# updates the code and rebuilds, and keeps the graph's runtime state unless you pass --reset-graph.
#
#   1. Create /opt/lore/.env by hand first (the variables are listed in README.md "Deploy").
#   2. scp -i lore.pem deploy/ec2-setup.sh ubuntu@<ip>:~ ; ssh -i lore.pem ubuntu@<ip> "bash ec2-setup.sh"
#      bash ec2-setup.sh --reset-graph                         # reload the graphs from the snapshot
#
# Nothing here fetches GitHub data for the graph or calls an LLM: the graphs come from the
# v0.1-snapshot release (lore.rdb, made by backend/scripts/snapshot.py on the dev machine).
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/im-Amrith/lore.git}"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/opt/lore}"
SNAPSHOT_URL="${SNAPSHOT_URL:-https://github.com/im-Amrith/lore/releases/download/v0.1-snapshot}"
RESET_GRAPH=0
[[ "${1:-}" == "--reset-graph" ]] && RESET_GRAPH=1

log() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
COMPOSE=(sudo docker compose --env-file "$APP_DIR/.env" -f "$APP_DIR/deploy/docker-compose.yml")

# ------------------------------------------------------------------ .env first (no secrets in git)
REQUIRED=(GITHUB_TOKEN DEMO_ORG SANDBOX_REPO LLM_FAST_API_KEY LLM_SMART_API_KEY GITHUB_WEBHOOK_SECRET
          TRIAGE_APPROVAL_SECRET CORS_ORIGINS LORE_DOMAIN)
if [[ ! -f "$APP_DIR/.env" ]]; then
  echo "Create $APP_DIR/.env first (sudo mkdir -p $APP_DIR && sudo nano $APP_DIR/.env)."
  echo "Required: ${REQUIRED[*]} (see README.md, Deploy)."
  exit 1
fi
missing=()
for v in "${REQUIRED[@]}"; do
  sudo grep -qE "^${v}=.+" "$APP_DIR/.env" || missing+=("$v")
done
if (( ${#missing[@]} )); then
  echo "Missing or empty in $APP_DIR/.env: ${missing[*]}"
  exit 1
fi
sudo chmod 600 "$APP_DIR/.env"

# ------------------------------------------------------------------ swap (4 GB RAM; builds like headroom)
if ! swapon --show | grep -q /swapfile; then
  log "Adding a 2 GB swap file"
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

# ------------------------------------------------------------------ Docker (official apt repo)
if ! command -v docker >/dev/null || ! sudo docker compose version >/dev/null 2>&1; then
  log "Installing Docker"
  sudo apt-get update -y
  sudo apt-get install -y ca-certificates curl git
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
sudo systemctl enable --now docker containerd >/dev/null  # back after a reboot; containers restart with it

# ------------------------------------------------------------------ the code
log "Fetching $REPO_URL ($BRANCH) into $APP_DIR"
if [[ -d "$APP_DIR/.git" ]]; then
  sudo git -C "$APP_DIR" fetch --depth 1 origin "$BRANCH"
  sudo git -C "$APP_DIR" reset --hard "origin/$BRANCH"   # .env and state/ are untracked and kept
else
  tmp="$(mktemp -d)"
  sudo git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$tmp/lore"
  sudo cp -a "$tmp/lore/." "$APP_DIR/"                    # APP_DIR already holds .env
  sudo rm -rf "$tmp"
fi

# ------------------------------------------------------------------ the snapshot (GitHub release)
SNAP="$APP_DIR/state/snapshot"
sudo mkdir -p "$SNAP" "$APP_DIR/state/falkordb" "$APP_DIR/state/cache/answers" "$APP_DIR/state/raw"
log "Downloading the graph snapshot"
for f in SHA256SUMS lore.rdb answers.tar.gz; do
  sudo curl -fsSL --retry 3 -o "$SNAP/$f.new" "$SNAPSHOT_URL/$f"
  sudo mv "$SNAP/$f.new" "$SNAP/$f"
done
(cd "$SNAP" && sudo sha256sum -c SHA256SUMS)

if (( RESET_GRAPH )) || [[ ! -f "$APP_DIR/state/falkordb/dump.rdb" ]]; then
  log "Seeding FalkorDB from the snapshot"
  "${COMPOSE[@]}" stop falkordb 2>/dev/null || true       # a running FalkorDB would save over it
  sudo cp "$SNAP/lore.rdb" "$APP_DIR/state/falkordb/dump.rdb"
else
  echo "FalkorDB data exists; keeping it (pass --reset-graph to reload the snapshot)."
fi
# Cached answers for exactly this graph: pre-warming costs no LLM calls for them. Existing files stay.
sudo tar -xzf "$SNAP/answers.tar.gz" -C "$APP_DIR/state/cache/answers" --skip-old-files

# ------------------------------------------------------------------ build and run
log "Building and starting FalkorDB, backend, Caddy"
"${COMPOSE[@]}" up -d --build --remove-orphans
sudo docker image prune -f >/dev/null
# M15: the sandbox's raw GitHub cache, fetched once (a merged PR's sync updates it). Kept in state/raw.
"${COMPOSE[@]}" exec -T backend .venv/bin/python scripts/sync.py --prime || echo "prime failed; the sync will retry"

DOMAIN="$(sudo grep -E '^LORE_DOMAIN=' "$APP_DIR/.env" | cut -d= -f2- | tr -d '"'"'"' ')"
log "Waiting for https://$DOMAIN/health (Caddy gets its certificate on the first request)"
for i in $(seq 1 60); do
  if curl -fsS --max-time 10 "https://$DOMAIN/health" >/dev/null 2>&1; then
    curl -fsS "https://$DOMAIN/health"; echo
    log "Lore is up: https://$DOMAIN (API docs: https://$DOMAIN/docs)"
    "${COMPOSE[@]}" ps
    exit 0
  fi
  sleep 5
done
echo "Not answering on https://$DOMAIN yet. Check: ${COMPOSE[*]} logs --tail 50"
exit 1
