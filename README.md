# VELRO

Station-based intercity transport for Afghanistan. A passenger books a seat on a
car that is going anyway; a driver fills the seats he would otherwise drive
empty. The pilot runs on three corridors out of Kabul — Charikar, Ghorband, and
between them — where travel already works this way, from a station, by shared
car, negotiated at the door.

The product is one backend and four clients: an Android and an iOS app for
passengers, the same two for drivers, a web panel for staff, and VELRO Ops, a
native console for iPhone, iPad, Mac and Apple Watch.

Everything speaks Dari, Pashto and English, with Eastern Arabic numerals and the
Afghan solar calendar — not as a translation layer added late, but as the
default the screens were laid out for.

## The repository

| Directory | What lives there |
|---|---|
| `backend/` | FastAPI + SQLAlchemy + PostgreSQL. Layered `domain / application / infrastructure / ui`, Alembic migrations, the three locale files, the OpenStreetMap extract the map endpoints serve. |
| `admin/` | The staff web panel. React, TypeScript, TanStack Query, MapLibre. |
| `ios/` | One Xcode project generated from `project.yml`: `VelroCore` (a Swift package shared by every target), `VelroPassenger`, `VelroDriver`, `VelroOps` (iOS + macOS), `VelroOpsWatch` and its complications. |
| `mobile/` | Android, two apps from one Gradle build: `app-passenger` and `app-driver`, over eleven modules. |
| `deploy/` | One VPS: Postgres, the API and Caddy in `docker-compose.yml`, plus the bootstrap, push and backup scripts. |
| `docs/` | Architecture decisions (`docs/adr`), the domain's lifecycles and calendar as data. |
| `data/` | Source material for the geography — the Ghorband villages and the script that converts them. |
| `scripts/` | `check.sh`, and the small tools for testing a real phone number. |

## Getting started

Each area stands on its own; you do not need the other three to work in one.

**Backend** — Python 3.12 and a local PostgreSQL:

```bash
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
createdb velro_dev && createdb velro_e2e
export VELRO_DATABASE_URL="postgresql+psycopg://$USER@localhost:5432/velro_dev"
export PYTHONPATH=.
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed.py
.venv/bin/python scripts/geography.py import
scripts/dev-api.sh          # the API on :8000
```

`dev-api.sh` turns OTP echo on, so the sign-in code comes back in the API
response and no handset is needed. `velro.toml` keeps it off, and
`shared/config.py` refuses it outright when the environment is production — so
the echo cannot follow a deployment out.

**Admin panel** — Node 22:

```bash
cd admin && npm install && npm run dev      # :5173, against the API on :8000
```

**iOS** — Xcode 16 or newer (Swift 6, iOS 17) and `xcodegen`. Every task has a make target, so Xcode never
has to be open:

```bash
cd ios
make api        # the local API
make run        # the passenger app on the simulator
make run APP=driver
make ops        # VELRO Ops (make ops-mac for the Mac build)
make core-test  # VelroCore on the Mac, seconds, no simulator
```

Debug builds always talk to `localhost`, never to production: a stray tap in the
simulator must not spend a real SMS.

**Android** — open the `mobile` folder in Android Studio, not the repository
root. Both apps point at `http://10.0.2.2:8000`, which is how the emulator
reaches a backend on the same machine. See `mobile/README.md` for real handsets
and for signing.

## Checks

One script, run identically by a person and by CI — a pipeline that runs
different commands from the ones developers use is a pipeline that fails for
reasons nobody can reproduce:

```bash
scripts/check.sh              # everything
scripts/check.sh backend      # or admin, or mobile
```

GitHub Actions runs the same script in three jobs on every push
(`.github/workflows/check.yml`). The integration and end-to-end tests want real
PostgreSQL: SQLite would not have caught `FOR UPDATE SKIP LOCKED` behaving
differently, and seat booking is the mechanic the product rests on.

## Languages

`backend/resources/locales/{en,fa-AF,ps}.json` are the single source of every
string; the web panel and the apps read the same keys, and the iOS test suite
fails on a key used in a screen but missing from a file. A new key is added to
all three files and gets a row in `REVIEW.tsv` so the Pashto can be checked by
somebody who speaks it.

## Deployment

`deploy/README.md` — one VPS, Docker Compose, Caddy terminating TLS;
`docs/adr/0011-deployment.md` says why that is the right amount of
infrastructure for a pilot in one valley rather than a corner cut for later.
Deploys are run by hand, from the server, by the owner.

## What never enters this repository

Nothing here is a secret, and nothing here should become one. Kept out by
`.gitignore`, on purpose:

- `.env` files, and `ios/scripts/.env` (the App Store Connect key that uploads
  builds as the account holder)
- the Android release keystore, `keystore.properties`, `*.jks`, `*.p8`
- `backend/var/` — drivers' uploaded identity documents
- `local.properties`, build output, and anything else that is a path on one
  machine

Signing keys and API keys live outside the working tree and reach a build
through the environment. Production secrets are set on the server and never
written to a file that git can see.

## Ownership

VELRO is a product of Linumic. Private repository; all rights reserved.
