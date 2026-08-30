# Deploying VELRO

One VPS. Postgres, the API, and Caddy in front of both, in `docker-compose.yml`.
No Kubernetes, no second region, no staging environment yet -- see
`docs/adr/0011-deployment.md` for why that is the right amount of
infrastructure for a pilot in one valley, not a corner cut for later.

## What only you can do

Nothing here can provision a server or touch DNS on your behalf -- both need
your account and your payment method.

1. **A VPS.** Recommendation: Hetzner Cloud, Falkenstein or Nuremberg,
   the smallest shared-vCPU plan with 4GB RAM (around €5/month at the time
   this was written -- confirm current pricing at signup). Docker and
   Docker Compose need to end up installed on it; Hetzner's App Marketplace
   has a "Docker CE" image that starts with both already there.

2. **Two DNS records**, at whoever hosts `linumic.com`'s DNS today:

   ```
   A    api.velro     <the VPS's IP address>
   A    admin.velro    <the VPS's IP address>
   ```

   Caddy requests a Let's Encrypt certificate for each domain the first time
   it sees a request for it, so there is no separate certificate step --
   only the DNS has to be pointing at the server before that first request
   arrives.

## First deploy

```bash
git clone <this repo> /opt/velro && cd /opt/velro

# The admin panel is a static build; Caddy serves it directly.
cd admin && npm ci && npm run build && cd ..

cd deploy
cp .env.example .env
# fill in .env: POSTGRES_PASSWORD, JWT_SECRET, and the four TWILIO_ values
# (openssl rand -hex 24 / -hex 32 for the first two)

docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python scripts/seed.py   # first deploy only
```

Then confirm it is actually alive:

```bash
curl https://api.velro.linumic.com/readyz
```

## Redeploying

```bash
cd /opt/velro && git pull
cd admin && npm run build && cd ..
cd deploy && docker compose up -d --build api
docker compose exec api alembic upgrade head   # no-op if nothing changed
```

`db` and `caddy` are not rebuilt on a normal deploy -- only `api` and the
admin static files change on an ordinary release.

## Backups

`backup.sh` does a nightly `pg_dump`, gzips it, and pushes it off the VPS via
`rclone` to wherever `RCLONE_REMOTE` in its environment points -- a Hetzner
Storage Box, Backblaze B2, anywhere `rclone` can reach. It refuses to run
silently without that: unset, it still writes the dump locally but says so
loudly, because a backup that lives only on the disk that might fail is not
a backup against that failure.

```bash
crontab -e
# 0 2 * * * RCLONE_REMOTE=<your-remote>:velro-backups /opt/velro/deploy/backup.sh >> /var/log/velro-backup.log 2>&1
```

Setting up the remote itself -- an rclone config with real credentials --
is the other thing only you can do here.
