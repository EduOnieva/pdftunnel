import pytest

from tests.conftest import PDF


async def test_inline_pdf_with_encoded_name(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert response.content == PDF
    headers = response.headers
    assert headers["content-type"] == "application/pdf"
    assert headers["content-disposition"] == "inline; filename*=utf-8''Cat%C3%A1logo%202026.pdf"
    assert headers["cache-control"] == "public, max-age=300"
    assert headers["accept-ranges"] == "bytes"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "etag" in headers and "last-modified" in headers
    assert "server" not in headers


async def test_attachment(client):
    response = await client.get("/download")
    assert response.headers["content-disposition"] == 'attachment; filename="catalogue.pdf"'


async def test_head(client):
    response = await client.head("/")
    assert response.status_code == 200 and response.content == b""
    assert int(response.headers["content-length"]) == len(PDF)


async def test_range(client):
    response = await client.get("/", headers={"Range": "bytes=0-7"})
    assert response.status_code == 206
    assert response.content == PDF[:8]
    assert response.headers["content-range"] == f"bytes 0-7/{len(PDF)}"


async def test_range_not_satisfiable(client):
    response = await client.get("/", headers={"Range": "bytes=99999-"})
    assert response.status_code == 416


async def test_conditional(client):
    first = await client.get("/")
    etag, modified = first.headers["etag"], first.headers["last-modified"]
    again = await client.get("/", headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.content == b""
    assert again.headers["etag"] == etag and again.headers["cache-control"].startswith("public")
    weak = await client.get("/", headers={"If-None-Match": f'W/{etag}, "other"'})
    assert weak.status_code == 304
    assert (await client.get("/", headers={"If-None-Match": '"other"'})).status_code == 200
    assert (await client.get("/", headers={"If-Modified-Since": modified})).status_code == 304
    old = "Mon, 01 Jan 2001 00:00:00 GMT"
    assert (await client.get("/", headers={"If-Modified-Since": old})).status_code == 200
    assert (await client.get("/", headers={"If-Modified-Since": "garbage"})).status_code == 200
    ranged = await client.get("/", headers={"If-None-Match": etag, "Range": "bytes=0-1"})
    assert ranged.status_code == 206


async def test_folder_file_and_text(client):
    pdf = await client.get("/docs/a.pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["content-disposition"] == 'inline; filename="a.pdf"'
    txt = await client.get("/docs/b.txt")
    assert txt.status_code == 200 and txt.headers["content-type"].startswith("text/plain")
    assert txt.text == "hello\n"


async def test_secret_link_works_without_login(client):
    assert (await client.get("/secret-k7f3q9x2")).status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/old.pdf",
        "/catalogue.pdf",
        "/files/catalogue.pdf",
        "/missing",
        "/docs/.hidden",
        "/docs/sub",
        "/docs/nope.pdf",
        "/plain/",
        "/%2e%2e/outside.txt",
        "/docs/%2e%2e/old.pdf",
        "/docs/../old.pdf",
        "/escape.txt",
        "/nope",
        "/_pdftunnel/nope.css",
        "/api/nope",
    ],
)
async def test_not_found(client, path):
    response = await client.get(path)
    assert response.status_code == 404
    assert response.text == "Not found\n"
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_other_methods_are_refused(client):
    assert (await client.post("/")).status_code == 405
    assert (await client.delete("/docs/a.pdf")).status_code == 405


async def test_access_route_without_token(client, caplog):
    response = await client.get("/private")
    assert response.status_code == 403
    assert response.headers["cache-control"] == "private, no-store"
    assert "no Access token" in caplog.text


async def test_access_route_with_bad_token(client, caplog):
    other = __import__("tests.fakes.access", fromlist=["FakeKeys"]).FakeKeys()
    response = await client.get("/private", headers={"Cf-Access-Jwt-Assertion": other.token()})
    assert response.status_code == 403
    assert "refused" in caplog.text


async def test_access_route_with_valid_token(client, keys):
    response = await client.get("/private", headers={"Cf-Access-Jwt-Assertion": keys.token()})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"


async def test_access_route_when_verification_is_unconfigured(client, deps, caplog):
    deps.source.verifier = None
    response = await client.get("/private")
    assert response.status_code == 403
    assert "access: is not configured" in caplog.text


async def test_counters_count_opens_only(client, deps):
    await client.get("/")
    await client.get("/")
    await client.head("/")
    await client.get("/", headers={"Range": "bytes=0-1"})
    await client.get("/docs/a.pdf")
    await client.get("/nope")
    assert deps.counters.snapshot() == {"/": 2, "/docs/": 1}


async def test_cache_max_age_zero(client, deps):
    from tests.web.conftest import make_config

    deps.source.reconfigure(make_config(cache={"max_age": 0}))
    response = await client.get("/")
    assert response.headers["cache-control"] == "no-cache"


async def test_stylesheets(client, deps, tmp_path):
    css = await client.get("/_pdftunnel/app.css")
    assert css.status_code == 200 and css.headers["content-type"].startswith("text/css")
    assert (await client.get("/_pdftunnel/custom.css")).status_code == 404
    custom = tmp_path / "custom.css"
    custom.write_text("h1 { color: red }")
    deps.custom_css = str(custom)
    response = await client.get("/_pdftunnel/custom.css")
    assert response.status_code == 200 and "red" in response.text


async def test_access_log_line(client, caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="pdftunnel.access"):
        await client.get("/docs/a.pdf", headers={"CF-Connecting-IP": "203.0.113.9"})
        await client.get("/healthz")
    lines = [r.getMessage() for r in caplog.records if r.name == "pdftunnel.access"]
    assert any(line.startswith("203.0.113.9 GET /docs/a.pdf 200") for line in lines)
    assert not any("/healthz" in line for line in lines)  # quiet path
