#!/usr/bin/env bash
# Print the newest cloudflared release tag that has been on Docker Hub for at least N days
# (default 7): a grace period in the spirit of Dependabot's cooldown, so a release that turns
# out to be broken or compromised is usually pulled before it reaches an image. A tag pushed
# again gets a new date on Docker Hub, so a silently replaced release waits too. Shorter than
# Dependabot's 14 days because cloudflared's own fixes wait the same time.
set -euo pipefail

DAYS="${1:-7}"
API="https://hub.docker.com/v2/repositories/cloudflare/cloudflared/tags?page_size=100&ordering=last_updated"

curl -fsS "$API" | python3 -c '
import json, re, sys
from datetime import datetime, timedelta, timezone

days = int(sys.argv[1])
cutoff = datetime.now(timezone.utc) - timedelta(days=days)
release = re.compile(r"^(\d{4})\.(\d{1,2})\.(\d+)$")
candidates = []
for tag in json.load(sys.stdin)["results"]:
    match = release.match(tag["name"])
    pushed = datetime.fromisoformat(tag["last_updated"].replace("Z", "+00:00"))
    if match and pushed <= cutoff:
        candidates.append((tuple(int(g) for g in match.groups()), tag["name"], pushed.date()))
if not candidates:
    sys.exit("no cloudflared release older than %d days among the newest 100 tags" % days)
version, name, pushed = max(candidates)
print(name)
print("pushed %s" % pushed, file=sys.stderr)
' "$DAYS"
