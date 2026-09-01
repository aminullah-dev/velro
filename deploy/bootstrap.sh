#!/usr/bin/env bash
# Bring VELRO up on a fresh server, or bring an existing one up to date.
#
#   /opt/velro/deploy/bootstrap.sh
#
# Safe to run again: every step it takes is one that can be taken twice.
# It stops with an explanation rather than guessing, because the failures
# that matter here are configuration ones and they are much cheaper to read
# than to debug through three containers.
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
stop() { printf '\n\033[31mstopped: %s\033[0m\n' "$*" >&2; exit 1; }

# -- preconditions -------------------------------------------------------
# Checked first and by name. The most likely mistake is running this on the
# laptop the code was written on, where none of it applies.

[ "$(uname -s)" = "Linux" ] || stop \
  "this runs on the server, not on a laptop.
   Get a VPS first, then: ssh root@<vps>, clone the repo to /opt/velro,
   and run this script there. On a Mac it would only start containers
   nobody can reach at a domain that points somewhere else."

command -v docker >/dev/null || stop \
  "docker is not installed.
   On Debian/Ubuntu:  curl -fsSL https://get.docker.com | sh"

docker compose version >/dev/null 2>&1 || stop \
  "the docker compose plugin is missing (docker compose, not docker-compose).
   On Debian/Ubuntu:  apt-get install -y docker-compose-plugin"

if [ ! -f .env ]; then
  cp .env.example .env
  stop ".env did not exist, so it has been created from the template.
   Open deploy/.env and fill in at least:
     POSTGRES_PASSWORD   openssl rand -hex 24
     JWT_SECRET          openssl rand -hex 32
   Leave VELRO_ENVIRONMENT=staging until real Twilio credentials exist --
   production refuses to start without a real SMS provider, on purpose.
   Then run this script again."
fi

grep -q '^POSTGRES_PASSWORD=.\+' .env || stop "POSTGRES_PASSWORD is empty in deploy/.env"
grep -q '^JWT_SECRET=.\{32,\}'    .env || stop "JWT_SECRET in deploy/.env must be at least 32 characters"

# -- the deploy itself ---------------------------------------------------

say "Building the admin panel (in Docker, so this server needs no Node)"
docker compose run --rm admin-build

say "Starting the database, the API and Caddy"
docker compose up -d --build

say "Waiting for the database"
for _ in $(seq 1 60); do
  docker compose exec -T db pg_isready -U velro >/dev/null 2>&1 && break
  sleep 2
done
docker compose exec -T db pg_isready -U velro >/dev/null 2>&1 \
  || stop "the database never became ready -- docker compose logs db"

say "Applying migrations"
docker compose exec -T api alembic upgrade head

# Seeding is only for a database that has never been seeded. seed.py is
# idempotent about places, but it also schedules trips, and a second run
# would schedule a second set of them onto a live product.
villages=$(docker compose exec -T db psql -U velro -d velro -tAc \
  "SELECT count(*) FROM villages" 2>/dev/null || echo 0)
if [ "${villages//[!0-9]/}" = "0" ]; then
  say "First deploy: seeding, and importing the real geography"
  docker compose exec -T api python scripts/seed.py
else
  say "Database already holds $villages villages -- importing geography only"
  docker compose exec -T api python scripts/geography.py import
fi

say "Checking it is actually serving"
for _ in $(seq 1 30); do
  docker compose exec -T api python -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:8000/readyz')" \
    >/dev/null 2>&1 && break
  sleep 2
done
docker compose exec -T api python -c \
  "import urllib.request; urllib.request.urlopen('http://localhost:8000/readyz')" \
  >/dev/null 2>&1 || stop "the API is up but not ready -- docker compose logs api"

cat <<'DONE'

Up.

  https://api.velro.linumic.com/readyz     the API
  https://admin.velro.linumic.com          the admin panel
  https://api.velro.linumic.com/app        where people download the apps

Certificates arrive by themselves the first time each domain is requested,
provided its DNS A record already points here.

Two things left, both from the laptop that holds the signing key:

  cd backend && scripts/publish-apks.sh https://api.velro.linumic.com/api/v1/
  scp backend/var/apks/velro-*.apk backend/var/apks/release.json root@<vps>:/tmp/
  ssh root@<vps> 'cd /opt/velro/deploy && for f in velro-passenger.apk velro-driver.apk release.json; do docker compose cp /tmp/$f api:/app/var/apks/$f; done'

And the nightly backup, which nothing else will set up for you:

  crontab -e
  0 2 * * * RCLONE_REMOTE=<remote>:velro-backups /opt/velro/deploy/backup.sh >> /var/log/velro-backup.log 2>&1
DONE
