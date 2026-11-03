from pdftunnel.config.schema import Route, SiteConfig
from tests.web.conftest import make_config


async def test_index_lists_the_listed_routes(client):
    response = await client.get("/", headers={"Accept": "text/html"})
    # / is a file route here, so the index is not shown there
    assert response.headers["content-type"] == "application/pdf"


async def test_index_page(client, deps):
    routes = [r for r in deps.source.config.routes if r.path != "/"]
    deps.source.reconfigure(make_config(routes=routes))
    response = await client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "<title>Test site</title>" in html
    assert 'href="/download"' in html and 'href="/docs/"' in html and "Documents" in html
    assert "secret-k7f3q9x2" not in html  # listed: false
    assert 'href="/private"' in html and "login" in html
    assert "B · " in html  # size and date of an existing file
    assert response.headers["content-security-policy"].startswith("default-src 'none'")
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-cache"
    assert "custom.css" not in html


async def test_index_links_custom_css(client, deps, tmp_path):
    deps.source.reconfigure(make_config(routes=[Route(path="/a", file="catalogue.pdf")]))
    deps.custom_css = str(tmp_path / "custom.css")
    assert "/_pdftunnel/custom.css" in (await client.get("/")).text


async def test_index_off(client, deps):
    deps.source.reconfigure(make_config(routes=[], site=SiteConfig(index=False)))
    assert (await client.get("/")).status_code == 404


async def test_index_empty(client, deps):
    deps.source.reconfigure(make_config(routes=[]))
    assert "Nothing published yet" in (await client.get("/")).text


async def test_listing_page(client):
    response = await client.get("/docs/")
    assert response.status_code == 200
    html = response.text
    assert "<title>Documents</title>" in html
    assert 'href="/docs/a.pdf"' in html and 'href="/docs/b.txt"' in html
    assert ".hidden" not in html and "sub" not in html
    assert "&lt;" not in html


async def test_listing_escapes_names(client, deps):
    (deps.source.paths.files_dir / "docs" / "<b>.txt").write_text("x")
    html = (await client.get("/docs/")).text
    assert "&lt;b&gt;.txt" in html and "<b>.txt" not in html


async def test_listing_empty(client, deps):
    (deps.source.paths.files_dir / "empty").mkdir()
    deps.source.reconfigure(make_config(routes=[Route(path="/e/", dir="empty", listing=True)]))
    assert "This folder is empty" in (await client.get("/e/")).text


def test_human_size():
    from pdftunnel.web.pages import human_size

    assert human_size(0) == "0 B"
    assert human_size(999) == "999 B"
    assert human_size(2048) == "2.0 KB"
    assert human_size(5 * 1024 * 1024) == "5.0 MB"
    assert human_size(3 * 1024**3) == "3.0 GB"
    assert human_size(3000 * 1024**3) == "3000.0 GB"
