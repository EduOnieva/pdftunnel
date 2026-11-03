# pdftunnel

Publish PDFs and other files from a folder through a Cloudflare Tunnel. One container, one
volume, nothing published on your network.

The [README](https://github.com/EduOnieva/pdftunnel#readme) is the front page: what it does,
the quick start, the configuration tables. This wiki holds the longer guides.

## Setting up

- [[Installation]]: the compose file, the folder and its owner, secrets, the hardening, image
  tags and updating.
- [[Cloudflare]]: the tunnel and its public hostname, the cache, Cloudflare Access, step by
  step.
- [[Configuration]]: every environment variable and every `config.yaml` key, with examples.

## Running it

- [[Operations]]: replacing a file, logs, counters, the CLI, backing up `config/`.
- [[Troubleshooting]]: message by message.
- [[API]]: the status endpoint, with widgets for Homepage and Home Assistant.

## The project

- [[Development]]: code layout, tests, CI, the release flow.
- [Changelog](https://github.com/EduOnieva/pdftunnel/blob/main/CHANGELOG.md) and
  [security policy](https://github.com/EduOnieva/pdftunnel/blob/main/SECURITY.md).
