#!/usr/bin/env bash
# Smoke test of a built image: start it the way the compose file does (read-only, no
# capabilities, unprivileged user) with a bogus tunnel token and a mapped port, fetch a file,
# check the headers and the endpoints, then stop it and expect a clean exit.
set -euo pipefail

IMAGE="${1:-pdftunnel:dev}"
NAME="pdftunnel-smoke-$$"
WORK="$(mktemp -d)"
trap 'docker rm -f "$NAME" >/dev/null 2>&1 || true; rm -rf "$WORK" 2>/dev/null || true' EXIT

mkdir -p "$WORK/config/files/docs"
printf '%%PDF-1.4\n%%%%EOF\n' > "$WORK/config/files/catalogue.pdf"
printf '%%PDF-1.4\n%%%%EOF\n' > "$WORK/config/files/old.pdf"
printf 'hello\n' > "$WORK/config/files/docs/a.txt"
cat > "$WORK/config/config.yaml" <<'YAML'
routes:
  - path: /
    file: catalogue.pdf
    filename: "Catálogo.pdf"
  - path: /docs/
    dir: docs
    listing: true
YAML
chmod -R a+rwX "$WORK/config"

echo "== --version, check-config, token"
docker run --rm "$IMAGE" --version
docker run --rm -v "$WORK/config:/config" "$IMAGE" check-config
docker run --rm "$IMAGE" token | grep -Eq '^[a-z0-9]{12}$'

echo "== start"
# As the caller's own user, the way the compose file's `user:` override runs it, so the state
# the container writes can be cleaned up afterwards
docker run -d --name "$NAME" --user "$(id -u):$(id -g)" \
  --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true \
  -v "$WORK/config:/config" \
  -e TUNNEL_TOKEN=bogus -e API_TOKEN=smoke -e WEB_BIND=0.0.0.0 -p 127.0.0.1::8080 \
  "$IMAGE" >/dev/null
PORT="$(docker port "$NAME" 8080 | head -1 | sed 's/.*://')"
BASE="http://127.0.0.1:$PORT"
for _ in $(seq 1 50); do
  curl -fs -o /dev/null "$BASE/_pdftunnel/app.css" && break
  sleep 0.2
done

fail() { echo "FAIL: $*" >&2; docker logs "$NAME" >&2; exit 1; }

echo "== the file"
HEADERS="$(curl -s -D - -o "$WORK/got.pdf" "$BASE/")"
grep -qi '^HTTP/1.1 200' <<<"$HEADERS" || fail "GET / is not 200: $HEADERS"
grep -qi '^content-type: application/pdf' <<<"$HEADERS" || fail "content-type"
grep -qi "^content-disposition: inline; filename\*=utf-8''Cat%C3%A1logo.pdf" <<<"$HEADERS" || fail "disposition"
grep -qi '^cache-control: public, max-age=300' <<<"$HEADERS" || fail "cache-control"
grep -qi '^x-content-type-options: nosniff' <<<"$HEADERS" || fail "nosniff"
grep -qi '^server:' <<<"$HEADERS" && fail "server header present"
cmp -s "$WORK/got.pdf" "$WORK/config/files/catalogue.pdf" || fail "body differs"
[ "$(curl -s -o /dev/null -w '%{http_code}' -H 'Range: bytes=0-3' "$BASE/")" = 206 ] || fail "range"

echo "== what must not be served"
for path in /old.pdf /catalogue.pdf /files/catalogue.pdf /docs/../old.pdf /nope; do
  code="$(curl -s --path-as-is -o /dev/null -w '%{http_code}' "$BASE$path")"
  [ "$code" = 404 ] || fail "$path returned $code"
done

echo "== listing, health, status"
curl -s "$BASE/docs/" | grep -q 'href="/docs/a.txt"' || fail "listing"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/healthz")" = 503 ] || fail "healthz should be 503 with a bogus token"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/status")" = 401 ] || fail "status without token"
STATUS="$(curl -s -H 'Authorization: Bearer smoke' "$BASE/api/status")"
grep -q '"state": *"\(down\|connecting\)"' <<<"$STATUS" || fail "tunnel state: $STATUS"
grep -q '"path": *"/"' <<<"$STATUS" || fail "routes in status"
docker exec "$NAME" pdftunnel healthcheck && fail "healthcheck should fail" || true

echo "== restart loop is running"
docker logs "$NAME" 2>&1 | grep -q 'restarting in' || fail "no restart line in the log"

echo "== stop"
docker stop -t 15 "$NAME" >/dev/null
EXIT="$(docker inspect -f '{{.State.ExitCode}}' "$NAME")"
[ "$EXIT" = 0 ] || fail "exit code $EXIT"
docker logs "$NAME" 2>&1 | grep -q 'Stopped' || fail "no Stopped line"
[ -f "$WORK/config/state/counters.json" ] || fail "counters not written"
grep -q 'Tunnel connected' <(docker logs "$NAME" 2>&1) && fail "connected with a bogus token?" || true

echo "OK"
