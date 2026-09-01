# Production image for the VELRO API.
#
# Single stage, plain pip: the backend has no compiled step of its own and no
# lockfile to reproduce, so a multi-stage build would buy nothing here that a
# slim base image and --no-cache-dir don't already give.
FROM python:3.12-slim

# psycopg[binary] ships its own libpq, so this is only for build tooling that
# a couple of transitive C extensions still want at install time.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Not the usual "copy pyproject.toml first, install, then copy source" layer
# trick: [tool.setuptools] packages here are the source directories
# themselves (domain, application, infrastructure, shared, ui), so pip has
# nothing to install until they exist -- installing before COPY . . fails
# outright rather than merely losing the caching benefit. And editable mode
# has no purpose in an image that gets rebuilt on every deploy rather than
# edited live inside a running container, so this is a normal install.
COPY . .
RUN pip install --no-cache-dir .

# Uploaded documents -- tazkiras, licences, vehicle papers -- live under
# storage_root. This is where the compose file mounts a real volume; without
# a declared mount point here a redeploy would silently lose them to the
# container filesystem.
RUN mkdir -p /app/var/storage

# Not root. A container that only ever serves HTTP over a reverse proxy has no
# business running as the user that owns the filesystem it's on.
RUN useradd --create-home --uid 1000 velro && chown -R velro:velro /app
USER velro

EXPOSE 8000

# One worker per core is a starting point, not a promise -- tuned against the
# VPS actually chosen, not guessed at here. Access logs go to Caddy, which
# already logs every request with a request ID; a second copy from uvicorn
# would just be noise in the same stream.
# --proxy-headers with a wildcard trust, and both halves are deliberate.
#
# Caddy terminates TLS and forwards over the compose network, so it arrives
# from a container address, not 127.0.0.1 -- which is all uvicorn trusts by
# default. Untrusted means X-Forwarded-Proto is ignored, request.base_url
# comes out http, and the map style hands the apps http:// tile URLs that a
# release build refuses outright: the map simply does not draw, in
# production only, for a reason nothing in the app can explain.
#
# The wildcard is safe here precisely because of what the compose file does
# NOT do: port 8000 is never published, so the only thing that can reach
# this process is Caddy on the internal network. If that ever changes, this
# has to change with it.
CMD ["uvicorn", "ui.api.app:asgi", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--no-access-log", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
