import pytest

from pdftunnel.config.schema import Config, Route
from pdftunnel.serve.routes import FileMatch, ListingMatch, RouteTable


@pytest.fixture
def table(paths) -> RouteTable:
    config = Config(
        routes=[
            Route(path="/", file="catalogue.pdf", filename="Catálogo.pdf"),
            Route(path="/docs/", dir="docs", listing=True),
            Route(path="/docs/sub/", dir="docs/sub"),
            Route(path="/missing", file="gone.pdf"),
            Route(path="/escape", file="escape.txt"),
            Route(path="/nolist/", dir="docs"),
        ]
    )
    return RouteTable(config, paths.files_dir)


def test_file_route(table, paths):
    match = table.match("/")
    assert isinstance(match, FileMatch)
    assert match.path == (paths.files_dir / "catalogue.pdf").resolve()
    assert match.download_name == "Catálogo.pdf" and match.relative == "catalogue.pdf"


def test_download_name_defaults_to_the_file(table):
    match = table.match("/docs/a.pdf")
    assert isinstance(match, FileMatch) and match.download_name == "a.pdf"
    assert match.relative == "docs/a.pdf"


@pytest.mark.parametrize(
    "url",
    [
        "/old.pdf",  # exists, not routed
        "/catalogue.pdf",  # the file's real name is not a URL
        "/missing",  # routed, file gone
        "/escape",  # symlink out of files/
        "/docs/../old.pdf",
        "/docs/./a.pdf",
        "/docs//a.pdf",
        "/docs/.hidden",
        "/docs/sub",  # the folder itself without a slash
        "/docs/nope.pdf",
        "/nolist/",  # listing off
        "/nope",
        "/docs/a.pdf\x00",
    ],
)
def test_not_found(table, url):
    assert table.match(url) is None


def test_nested_file_and_longest_prefix(table):
    match = table.match("/docs/sub/deep.pdf")
    assert isinstance(match, FileMatch) and match.route.path == "/docs/sub/"
    assert match.relative == "docs/sub/deep.pdf"


def test_symlink_inside_files_is_fine(table, paths):
    match = table.match("/docs/alias.pdf")
    assert isinstance(match, FileMatch)
    assert match.path == (paths.files_dir / "catalogue.pdf").resolve()


def test_listing(table, paths):
    match = table.match("/docs/")
    assert isinstance(match, ListingMatch) and match.directory == paths.files_dir / "docs"
    names = [p.name for p in table.listing(match.directory)]
    assert names == ["a.pdf", "alias.pdf", "b.txt"]  # no dotfile, no sub folder


def test_listing_of_unreadable_dir_is_empty(table, tmp_path):
    assert table.listing(tmp_path / "nowhere") == []


def test_listing_at_missing_dir_is_not_found(paths):
    table = RouteTable(
        Config(routes=[Route(path="/x/", dir="nowhere", listing=True)]), paths.files_dir
    )
    assert table.match("/x/") is None


def test_file_for(table):
    routes = {r.path: r for r in table.routes}
    assert table.file_for(routes["/"]) is not None
    assert table.file_for(routes["/missing"]) is None
    assert table.file_for(routes["/docs/"]) is None
