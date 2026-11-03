# Changelog

## 1.0 - 2026-11-03

The first release. A rewrite of a one-file nginx and cloudflared container into a tool.

### Added
- Routes in `config.yaml`: a URL path to a file under `config/files`, or to a folder served
  under the path. Only routed files are reachable; dotfiles and symlinks that leave the folder
  are not.
- The right headers for a document: inline or attachment with a chosen name (RFC 5987 for
  accented characters), Range requests, ETag and Last-Modified with 304 answers,
  `Cache-Control` from `cache.max_age`, `nosniff` and a referrer policy.
- Secret links (an unguessable path, `pdftunnel token` prints one), folder listings, an
  optional index page at `/`, and `custom.css` to restyle the pages.
- Cloudflare Access verification per route (`access: true`): the `Cf-Access-Jwt-Assertion`
  token is checked against the team's keys and the application's audience, and the file goes
  out with `private, no-store`.
- cloudflared bundled from its official image and supervised by the application: started
  with the token in its environment, restarted with a backoff when it exits, stopped on
  SIGTERM. The tunnel's connections are read from its log.
- Hot reload of `config.yaml`; a broken edit keeps the previous configuration and is reported
  once in the log and in the status API.
- `/healthz` tied to the tunnel's connection, `/api/status` (bearer token or Access login)
  with every route's size, date, existence and open count, kept in `config/state`.
- The CLI: `run`, `check-config`, `print-config`, `print-example-config`, `token`,
  `healthcheck`.
- The image: Alpine, unprivileged user, no pip; the compose file runs it read-only with every
  capability dropped and no published port. Images for amd64 and arm64 on Docker Hub and
  GHCR, rebuilt weekly.
