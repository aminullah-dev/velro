# ADR 0011 — One VPS, Docker Compose, Caddy

## Status
Accepted, 30 August 2026.

## Context
VELRO has never run anywhere but a developer's laptop. Reaching a real person
in Ghorband means a server somewhere, a domain pointing at it, HTTPS, and a
way to get the database back after the disk that holds it fails.

The Enterprise Platform house style favours plain infrastructure over
orchestration until scale demands otherwise, and nothing about a pilot in
one valley demands otherwise yet: the whole product today is one FastAPI
process, one PostgreSQL database, and one static admin build. Kubernetes, a
service mesh, or multiple regions would each be a new way for an unattended
Friday-night deploy to fail, bought with nothing gained — there is no second
region's worth of users to serve, and no team on call to page.

The domain question resolved itself: Linumic (linumic.com), the user's
company, is VELRO's parent, so `*.velro.linumic.com` costs nothing beyond
two DNS records, where the earlier plan had assumed a domain would need
buying.

## Decision
**One VPS.** Hetzner Cloud, a European region (Falkenstein or Nuremberg),
sized for the traffic a valley pilot actually produces rather than for
growth that has not happened yet. Nothing here prevents moving later —
`docker compose` runs identically on a bigger box or a different provider,
which is the point of choosing it over anything more specific to one host.

**Three containers**: `db` (Postgres, no published port — nothing outside
this compose file has a reason to reach it directly), `api` (the FastAPI
image, `VELRO_ENVIRONMENT=production`), and `caddy` (reverse proxy,
automatic Let's Encrypt, and the admin panel's static files, since the
panel calls its own origin at a relative path and same-origin means no CORS
configuration has to be gotten right).

Two subdomains: `api.velro.linumic.com` for both mobile apps,
`admin.velro.linumic.com` for the browser panel and, proxied under
`/api/v1`, the same API.

**Backups leave the VPS.** `pg_dump`, nightly, gzipped, pushed off-box via
`rclone` to wherever the operator configures — a Hetzner Storage Box or
similar. A dump kept only on the disk it was taken from is not a backup
against the one failure most likely to need it.

**No staging environment yet.** The original foundation plan called for
three environments with separate secrets. That is still right for a
product handling money and identity documents, and premature for a single
pilot valley with no second developer yet contending for the same
database. The compose file does not preclude adding one — a second host
running the identical file is the whole migration.

## Consequences
Every production secret lives in one `.env` file, on one host, read by
`docker compose` and nowhere else. `deploy/.env.example` documents every
key; the real file is gitignored at the repo root pattern `.env.*`, which
was already in place and already correct — confirmed with `git
check-ignore` rather than assumed.

The mobile release build had been pointing at `https://api.velro.af`, a
placeholder from before the domain question was settled. Fixed to
`api.velro.linumic.com` in the same change that added this deployment —
otherwise the infrastructure and the app shipping against it would have
quietly disagreed about where the server was.

`otp_debug_echo` and `VELRO_SMS_PROVIDER=console` are both refused by
`config.load` in production (see the commit that added those guards). This
compose file does not set either, and the comment beside where they would
go says why: the guard exists so a debugging session cannot leave one on by
habit, and an env file that names the setting even to say "false" is a
smaller distance from that than an env file that never mentions it at all.

`docker` is not installed on the machine this was written on, so the compose
file cannot be run here. What could be checked was checked by a closer route:
a real, non-editable `pip install .` into a clean venv, from outside the
source tree, followed by actually starting `uvicorn ui.api.app:asgi` against
a live PostgreSQL and hitting `/readyz`. That is what a container does, run
without the container -- and it found three bugs a Docker build alone would
also have hit, none related to Docker itself:

- `[tool.setuptools] packages = [...]` listed only five top-level names, so a
  real install silently dropped every nested subpackage --
  `application.use_cases`, `infrastructure.db.models`, `ui.api.routers`, ten
  directories in all. Invisible until now because local dev has only ever
  used `pip install -e .`, whose editable finder resolves straight from the
  source tree regardless of what is declared. Fixed with
  `[tool.setuptools.packages.find]`.
- `httpx`, used by the Twilio sender's HTTP call, was listed only under the
  `dev` extra. Worked in every dev `.venv` because dev's own `httpx`, pulled
  in for `TestClient`, happened to share the interpreter. Moved to core
  dependencies.
- `cors_origins` and `supported_locales` were absent from `_DEFAULTS`, which
  is what `_coerce` checks to decide whether an env value should be split on
  commas. Absent, in `_coerce`'s terms, means "was never a tuple", so setting
  either by environment variable produced a bare string -- and
  `CORSMiddleware(allow_origins=list(cfg.cors_origins))` in `ui/api/app.py`
  turns a string into one entry per character. Dormant since nobody had ever
  set `VELRO_CORS_ORIGINS` before this compose file did. Both settings now
  have real tuple defaults.

None of the three would have shown up from reading the code -- every one of
them is invisible in the dev `.venv`, which is exactly why nobody had found
them. What surfaced them was running the actual install and the actual
process instead of assuming either would behave like the editable dev
checkout. The first real deploy is still the first time the *container* is
verified end to end; the *application* inside it has now been.
