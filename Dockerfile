# syntax=docker/dockerfile:1.7
# pdftunnel: publish PDFs and other files from a folder through a Cloudflare Tunnel.
# Three stages: resolve the locked Python environment with uv, take cloudflared from its
# official image, and copy both onto a slim runtime that runs as an unprivileged user.

FROM python:3.13.18-alpine3.24 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /bin/uv
# UV_NO_BUILD: a dependency without a musl wheel fails the build here instead of compiling quietly
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_BUILD=1 UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /build
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-editable

# The static cloudflared binary, from the image Cloudflare publishes; Dependabot bumps this tag
FROM cloudflare/cloudflared:2026.10.7 AS cloudflared

FROM python:3.13.18-alpine3.24
# pip, ensurepip, idle and pydoc never run here; pip's vendored packages are what image
# scanners flag, so they leave with it
RUN apk add --no-cache tini tzdata ca-certificates \
    && rm -rf /usr/local/lib/python3.13/site-packages/pip* \
              /usr/local/lib/python3.13/ensurepip \
              /usr/local/lib/python3.13/idlelib \
              /usr/local/bin/pip* /usr/local/bin/idle* /usr/local/bin/pydoc* /usr/local/bin/*-config \
    && addgroup -g 1000 pdftunnel \
    && adduser -D -u 1000 -G pdftunnel -h /home/pdftunnel pdftunnel \
    && mkdir -p /config && chown pdftunnel:pdftunnel /config
COPY --from=cloudflared /usr/local/bin/cloudflared /usr/local/bin/cloudflared
COPY --from=builder /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CONFIG_DIR=/config \
    TZ=Etc/UTC
USER pdftunnel
VOLUME ["/config"]
# Informational: the server listens on the loopback interface unless WEB_BIND says otherwise
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["pdftunnel", "healthcheck"]
ENTRYPOINT ["/sbin/tini", "--", "pdftunnel"]
CMD ["run"]
