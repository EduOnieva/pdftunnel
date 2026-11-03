# Cloudflare

Everything on the Cloudflare side, screen by screen. You need a domain on Cloudflare (any
plan, Free included) and a Zero Trust account, which is free for this use.

## The tunnel

1. [Zero Trust](https://one.dash.cloudflare.com/) > *Networks* > *Tunnels* > *Create a
   tunnel* > *Select Cloudflared*. Name it, for example `pdftunnel`.
2. The next screen shows install commands for several platforms. Each ends in
   `--token eyJ...`; that string is `TUNNEL_TOKEN`. Ignore the rest of the command: the
   container runs cloudflared itself.
3. *Public Hostname* tab > *Add a public hostname*: the subdomain and domain you want
   (`docs.example.com`), path empty, service type **HTTP**, URL `localhost:8080`.
4. Save. Once the container is running, the tunnel shows *Healthy* with the connectors it
   made (two by default, in two Cloudflare locations).

Several hostnames can point at the same tunnel and the same service: pdftunnel does not look
at the hostname, so each hostname sees the same routes.

The token identifies the tunnel to Cloudflare; whoever has it can run a connector for your
hostname. Rotate it from the tunnel's page (*Refresh token*) if it leaks, and update `.env`.

## The cache

Cloudflare caches responses whose extension it considers static, PDF among them, and honours
`Cache-Control`. pdftunnel sends `public, max-age=300` by default (`cache.max_age`), so after
you replace a file some visitors see the old one for up to five minutes. For a change that
must be instant: *your domain* > *Caching* > *Configuration* > *Purge Cache* > *Custom
Purge* > the URL. `max_age: 0` sends `no-cache`, which makes Cloudflare revalidate every
request with the container (one small 304 round trip per visit; files behind Access are never
cached by Cloudflare at all).

Routes without an extension (`/`, `/prices-k7f3q9x2`) are cached according to the headers
as well; Cloudflare's *Cache Rules* can change that per path.

## Cloudflare Access

For a document that must sit behind a login.

1. Zero Trust > *Access* > *Applications* > *Add an application* > *Self-hosted*.
2. Application domain: your hostname, and a path if only part of it is protected
   (`docs.example.com` with path `internal` covers `/internal/...`). Session duration as you
   like.
3. Add a policy: *Allow*, with the rule that fits (emails, an email domain, a login method).
4. Save, then open the application's *Overview*: copy the *Application Audience (AUD) Tag*.
5. In `config.yaml`:

   ```yaml
   access:
     team_domain: myteam.cloudflareaccess.com   # Zero Trust > Settings > Custom Pages shows it
     audience: "<the AUD tag>"
   routes:
     - path: /internal/
       dir: internal
       access: true
   ```

Cloudflare now shows a login page before anything under the application's path reaches the
container, and adds a `Cf-Access-Jwt-Assertion` header to the requests it lets through.
pdftunnel verifies that token on every `access: true` route: signature against the team's
public keys (fetched from `https://<team_domain>/cdn-cgi/access/certs` and cached for an
hour), expiry, the issuer and the audience. A request without a valid token gets a 403 even
if it somehow reached the container, which is what makes a forgotten policy or a mapped port
safe.

Two things to keep straight:

- The Access application's path and the routes marked `access: true` should cover the same
  URLs. A route with `access: true` outside the application's path is always 403, since
  Cloudflare never adds the token there. A route inside the application's path without
  `access: true` is served to logged-in visitors only, by Cloudflare, with pdftunnel treating
  it as public (and cacheable).
- One `audience` per container. Several Access applications with different AUD tags would
  need several containers, or one application covering all the protected paths.

`/api/status` accepts an Access login as well, so a browser that is logged in can open it
without the bearer token when the application covers `/api`.
