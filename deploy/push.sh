#!/usr/bin/env bash
# Send this working tree to the server and deploy it.
#
#   deploy/push.sh                      # the usual: velro-prod
#   VELRO_HOST=1.2.3.4 deploy/push.sh   # somewhere else
#
# rsync rather than git, because that is how this server was built and it
# needs no credentials on the server at all: the laptop already has ssh
# access, and giving a VPS read access to a private repository is a key to
# manage, rotate and eventually forget about.
#
# What does NOT travel: the mobile app (the server never builds it), any
# virtualenv or node_modules (the wrong operating system's binaries), the
# signing key, and deploy/.env -- the server's secrets are the server's, and
# a laptop overwriting them is how a deployment loses its database password.
set -euo pipefail

HOST="${VELRO_HOST:-62.238.0.71}"
KEY="${VELRO_SSH_KEY:-$HOME/.ssh/velro_hetzner}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

[ -f "$KEY" ] || { echo "no ssh key at $KEY" >&2; exit 1; }

echo "==> Sending $ROOT to $HOST:/opt/velro"
rsync -az --delete \
  -e "ssh -i $KEY -o BatchMode=yes" \
  --exclude '.git/' \
  --exclude 'mobile/' \
  --exclude 'deploy/.env' \
  --exclude '**/node_modules/' \
  --exclude '**/.venv/' \
  --exclude '**/build/' \
  --exclude '**/dist/' \
  --exclude '**/__pycache__/' \
  --exclude '**/.pytest_cache/' \
  --exclude '**/.ruff_cache/' \
  --exclude 'backend/var/' \
  --exclude '*.jks' \
  --exclude '*.keystore' \
  "$ROOT/" "root@$HOST:/opt/velro/"

echo "==> Deploying on the server"
ssh -i "$KEY" -o BatchMode=yes "root@$HOST" 'ALREADY_ON_SERVER=1 /opt/velro/deploy/bootstrap.sh'
