# Security

pdftunnel serves files to the public internet through a Cloudflare Tunnel. Its promise is
that only the files named in `config.yaml` are reachable, that a route marked `access: true`
is served only with a valid Cloudflare Access login, and that the tunnel token never leaves
the container's environment. A report that breaks any of these is what this policy is for; a
report about the web server being reachable on a mapped port with `WEB_BIND=0.0.0.0` is not,
since the README documents that as a testing setting that bypasses Cloudflare.

## Reporting a vulnerability

Report it privately through GitHub: the *Security* tab of the repository, *Report a
vulnerability*, or https://github.com/EduOnieva/pdftunnel/security/advisories/new.
Please do not describe it in a public pull request. Expect an answer within a week.

## Supported versions

The newest release only: `latest`, which is also the newest `X.Y` tag. A fix ships as a new
release, and the weekly rebuild of the release tags picks up fixes in the base image and
Alpine packages on its own; cloudflared is updated through Dependabot.
