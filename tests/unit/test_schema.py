import pytest
from pydantic import ValidationError

from pdftunnel.config.schema import (
    AccessConfig,
    Config,
    Disposition,
    Route,
    check_relative_file_path,
    normalise_url_path,
)


class TestNormaliseUrlPath:
    def test_root_and_plain_paths(self):
        assert normalise_url_path("/", folder=False) == "/"
        assert normalise_url_path("/a/b", folder=False) == "/a/b"
        assert normalise_url_path("/a/b/", folder=False) == "/a/b"

    def test_folder_gets_trailing_slash(self):
        assert normalise_url_path("/docs", folder=True) == "/docs/"
        assert normalise_url_path("/docs/", folder=True) == "/docs/"
        assert normalise_url_path("/", folder=True) == "/"

    @pytest.mark.parametrize("raw", ["docs", "/a//b", "/a/../b", "/a/./b", "/a?x=1", "/a#b"])
    def test_rejects(self, raw):
        with pytest.raises(ValueError):
            normalise_url_path(raw, folder=False)


class TestRelativeFilePath:
    def test_accepts_nested(self):
        assert check_relative_file_path("docs/sub/a.pdf") == "docs/sub/a.pdf"
        assert check_relative_file_path("./a.pdf") == "a.pdf"

    @pytest.mark.parametrize(
        "raw", ["", " a.pdf", "/etc/passwd", "../x.pdf", "a/../b", ".hidden", "d/.h/x"]
    )
    def test_rejects(self, raw):
        with pytest.raises(ValueError):
            check_relative_file_path(raw)


class TestRoute:
    def test_file_route_defaults(self):
        route = Route(path="/catalogue/", file="catalogue.pdf")
        assert route.path == "/catalogue"
        assert not route.is_dir
        assert route.disposition is Disposition.INLINE
        assert route.listed and not route.access and not route.listing
        assert route.label == "catalogue.pdf"

    def test_dir_route_gets_slash(self):
        route = Route(path="/docs", dir="docs")
        assert route.path == "/docs/"
        assert route.is_dir
        assert route.label == "/docs/"

    def test_labels(self):
        assert Route(path="/", file="a.pdf", filename="Nice.pdf").label == "Nice.pdf"
        assert Route(path="/", file="a.pdf", filename="Nice.pdf", title="T").label == "T"

    def test_needs_exactly_one_target(self):
        with pytest.raises(ValidationError, match="exactly one"):
            Route(path="/")
        with pytest.raises(ValidationError, match="exactly one"):
            Route(path="/", file="a.pdf", dir="docs")

    def test_listing_only_for_dirs(self):
        with pytest.raises(ValidationError, match="listing"):
            Route(path="/", file="a.pdf", listing=True)

    @pytest.mark.parametrize("path", ["/healthz", "/api", "/api/status", "/_pdftunnel/x"])
    def test_reserved_paths(self, path):
        with pytest.raises(ValidationError, match="reserved"):
            Route(path=path, file="a.pdf")

    def test_reserved_prefix_is_not_a_substring_match(self):
        assert Route(path="/apiary", file="a.pdf").path == "/apiary"

    @pytest.mark.parametrize("name", ["", " ", "a/b.pdf", 'a"b', "a\\b", "a\nb"])
    def test_bad_filename(self, name):
        with pytest.raises(ValidationError, match="plain file name"):
            Route(path="/", file="a.pdf", filename=name)

    def test_filename_is_stripped(self):
        assert Route(path="/", file="a.pdf", filename=" Catálogo.pdf ").filename == "Catálogo.pdf"

    def test_unknown_key_is_an_error(self):
        with pytest.raises(ValidationError, match="Extra inputs"):
            Route.model_validate({"path": "/", "file": "a.pdf", "flie": "typo"})


class TestAccessConfig:
    def test_not_configured(self):
        assert not AccessConfig().is_configured

    def test_team_name_becomes_domain(self):
        access = AccessConfig(team_domain="MyTeam", audience="x")
        assert access.team_domain == "myteam.cloudflareaccess.com"
        assert access.issuer == "https://myteam.cloudflareaccess.com"
        assert access.certs_url.endswith("/cdn-cgi/access/certs")
        assert access.is_configured

    def test_url_is_stripped(self):
        assert (
            AccessConfig(team_domain="https://t.cloudflareaccess.com/").team_domain
            == "t.cloudflareaccess.com"
        )

    @pytest.mark.parametrize("raw", ["", "  ", "bad domain", "x/y"])
    def test_rejects(self, raw):
        with pytest.raises(ValidationError):
            AccessConfig(team_domain=raw)


class TestConfig:
    def test_empty(self):
        config = Config()
        assert config.routes == [] and not config.site.index and config.cache.max_age == 300

    def test_duplicate_paths(self):
        with pytest.raises(ValidationError, match="configured twice"):
            Config(routes=[Route(path="/a", file="a.pdf"), Route(path="/a/", file="b.pdf")])

    def test_access_route_needs_access_config(self):
        with pytest.raises(ValidationError, match="team_domain and audience"):
            Config(routes=[Route(path="/a", file="a.pdf", access=True)])
        config = Config(
            routes=[Route(path="/a", file="a.pdf", access=True)],
            access=AccessConfig(team_domain="t", audience="aud"),
        )
        assert config.routes[0].access

    def test_listed_routes(self):
        config = Config(
            routes=[Route(path="/a", file="a.pdf"), Route(path="/b", file="b.pdf", listed=False)]
        )
        assert [r.path for r in config.listed_routes] == ["/a"]

    def test_negative_max_age(self):
        with pytest.raises(ValidationError):
            Config.model_validate({"cache": {"max_age": -1}})
