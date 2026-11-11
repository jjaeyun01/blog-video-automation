from __future__ import annotations

import gzip
import importlib

import pytest
import requests


@pytest.fixture
def crawler_module(monkeypatch):
    monkeypatch.syspath_prepend("scripts")
    return importlib.import_module("crawl_fevercoach_blog")


def test_normalizes_korean_urls_and_rejects_other_routes(crawler_module):
    normalize = crawler_module.post_url
    assert normalize("/ko/post/아이-열/?utm_source=x#test") == normalize("/ko/post/%EC%95%84%EC%9D%B4-%EC%97%B4")
    for value in ("https://elsewhere.test/ko/post/a", "/post/english", "/ko/blog", "/ko/post/", "/ko/post/a%2Fb"):
        assert normalize(value) is None


def test_sitemap_ignores_images_and_reads_gzip(crawler_module):
    xml = b'''<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
        <url><loc>https://www.fevercoach.us/ko/post/a</loc><lastmod>2026-10-10</lastmod>
        <image:image><image:loc>https://example.test/image.png</image:loc></image:image></url></urlset>'''
    assert crawler_module.sitemap_entries(gzip.compress(xml)) == (
        "urlset", [("https://www.fevercoach.us/ko/post/a", "2026-10-10")])


@pytest.mark.parametrize("language,prefix", [("ko", "/ko/post/"), ("en", "/post/"), ("es", "/es/post/")])
def test_language_routes_do_not_mix(crawler_module, language, prefix):
    assert crawler_module.post_url(prefix + "test/?utm=x#top", language=language) == crawler_module.ORIGIN + prefix + "test"
    for other in ("/ko/post/", "/post/", "/es/post/"):
        if other != prefix:
            assert crawler_module.post_url(other + "test", language=language) is None


@pytest.mark.parametrize("language", ["en", "es"])
def test_language_sitemap_and_pagination(crawler_module, language):
    origin = crawler_module.ORIGIN
    config = crawler_module.LANGUAGES[language]
    sitemap = origin + config["sitemap"]
    blog = origin + config["blog_path"]
    prefix = config["post_prefix"]
    declarations = "\n".join(f"Sitemap: {origin}{c['sitemap']}" for c in crawler_module.LANGUAGES.values())
    session = fake_session({
        origin + "/robots.txt": response("User-agent: *\nAllow: /\n" + declarations),
        sitemap: response(f"<urlset><url><loc>{origin}{prefix}a</loc></url><url><loc>{origin}/ko/post/other</loc></url></urlset>"),
        blog: response(f'<a href="{prefix}a">A</a><a href="?page=2">Next</a><a href="/ko/blog">KO</a>'),
        blog + "?page=2": response(f'<a href="{prefix}b">B</a><a href="{config["blog_path"]}">Previous</a>'),
    })
    crawler = crawler_module.BlogCrawler(language=language, session=session, delay=0)
    assert [p["slug"] for p in crawler.crawl()] == ["a", "b"]
    assert crawler.visited_sitemaps == [sitemap]
    assert crawler.visited_pages == [blog, blog + "?page=2"]
    assert not crawler.warnings


def response(body, status=200, headers=None):
    result = requests.Response()
    result.status_code = status
    result._content = body.encode("utf-8")
    result.encoding = "utf-8"
    result.headers.update(headers or {})
    return result


def fake_session(routes):
    class Session:
        headers = {}

        def __init__(self):
            self.calls = []

        def mount(self, *_):
            pass

        def get(self, url, **kwargs):
            self.calls.append(url)
            assert kwargs["allow_redirects"] is False
            return routes[url]
    return Session()


def test_nested_sitemaps_pagination_and_deduplication(crawler_module):
    origin = crawler_module.ORIGIN
    session = fake_session({
        origin + "/robots.txt": response(f"User-agent: *\nAllow: /\nSitemap: {origin}/ko_ko-sitemap.xml\nSitemap: https://external.test/sitemap.xml"),
        origin + "/ko_ko-sitemap.xml": response(f"<sitemapindex><sitemap><loc>{origin}/child.xml</loc></sitemap><sitemap><loc>https://external.test/probe.xml</loc></sitemap></sitemapindex>"),
        origin + "/child.xml": response(f"<urlset><url><loc>{origin}/ko/post/a</loc><lastmod>2026-10-10</lastmod></url><url><loc>{origin}/post/en</loc></url></urlset>"),
        origin + "/ko/blog": response('<a href="/ko/post/a?utm_source=x">Title A</a><a href="?page=2">Next</a>'),
        origin + "/ko/blog?page=2": response('<a href="/ko/post/b">Title B</a><a href="/ko/blog">Previous</a>'),
    })
    crawler = crawler_module.BlogCrawler(session=session, delay=0)
    posts = crawler.crawl()
    assert [p["slug"] for p in posts] == ["a", "b"]
    assert posts[0]["title"] == "Title A"
    assert len(posts[0]["sources"]) == 2
    assert not crawler.warnings
    assert len(session.calls) == 5


def test_external_redirect_is_not_followed(crawler_module):
    session = fake_session({crawler_module.BLOG: response("", 302, {"Location": "https://external.test/"})})
    crawler = crawler_module.BlogCrawler(session=session, delay=0)
    with pytest.raises(ValueError, match="External URL"):
        crawler.fetch(crawler_module.BLOG)
    assert len(session.calls) == 1


def test_robots_denial_is_respected(crawler_module):
    origin = crawler_module.ORIGIN
    session = fake_session({origin + "/robots.txt": response("User-agent: *\nDisallow: /")})
    crawler = crawler_module.BlogCrawler(session=session, delay=0)
    assert crawler.crawl() == []
    assert crawler.warnings
    assert session.calls == [origin + "/robots.txt"]


def test_partial_failure_preserves_discovered_links(crawler_module):
    origin = crawler_module.ORIGIN
    session = fake_session({
        origin + "/robots.txt": response("User-agent: *\nAllow: /"),
        origin + "/sitemap.xml": response("unavailable", 503),
        crawler_module.BLOG: response('<a href="/ko/post/only">Only</a>'),
    })
    crawler = crawler_module.BlogCrawler(session=session, delay=0)
    assert len(crawler.crawl()) == 1
    assert any("No sitemap" in warning for warning in crawler.warnings)
