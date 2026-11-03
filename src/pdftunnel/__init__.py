"""pdftunnel: publish PDFs and other files from a folder through a Cloudflare Tunnel."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pdftunnel")
except PackageNotFoundError:  # pragma: no cover - only when run from a bare checkout
    __version__ = "0.0"
