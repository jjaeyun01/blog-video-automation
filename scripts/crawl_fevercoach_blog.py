"""Collect public KO/EN/ES blog URLs without a browser or paid API.

Run: .venv/bin/python scripts/crawl_fevercoach_blog.py --output-dir outputs/blog_links
"""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys
import time
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ORIGIN = "https://www.fevercoach.us"
BLOG = ORIGIN + "/ko/blog"
LANGUAGES = {
    "ko": {"blog_path": "/ko/blog", "post_prefix": "/ko/post/", "sitemap": "/ko_ko-sitemap.xml"},
    "en": {"blog_path": "/blog", "post_prefix": "/post/", "sitemap": "/sitemap.xml"},
    "es": {"blog_path": "/es/blog", "post_prefix": "/es/post/", "sitemap": "/es_es-sitemap.xml"},
}
AGENT = "FeverCoachLinkCollector/1.0"


def same_origin(url: str) -> bool:
    parsed = urlsplit(url)
    return (parsed.scheme == "https" and parsed.netloc.lower() == "www.fevercoach.us")


def post_url(value: str, base: str | None = None, *, language: str = "ko") -> str | None:
    """Normalize encoded/unencoded slugs and drop tracking queries/fragments."""
    config = LANGUAGES[language]
    url = urljoin(base or ORIGIN + config["blog_path"], value.strip())
    if not same_origin(url):
        return None
    parsed = urlsplit(url)
    path = unquote(parsed.path).rstrip("/")
    prefix = config["post_prefix"]
    if not path.startswith(prefix) or not path.removeprefix(prefix):
        return None
    # A post slug is one path segment. Reject encoded slashes too.
    if "/" in path.removeprefix(prefix):
        return None
    return urlunsplit(("https", "www.fevercoach.us", quote(path, safe="/-._~"), "", ""))


def sitemap_entries(content: bytes) -> tuple[str, list[tuple[str, str | None]]]:
    if content.startswith(b"\x1f\x8b"):
        content = gzip.decompress(content)
    root = ET.fromstring(content)
    kind = root.tag.rsplit("}", 1)[-1]
    if kind not in {"sitemapindex", "urlset"}:
        raise ValueError(f"Unexpected sitemap root: {kind}")
    entries = []
    for entry in root:
        # Direct children only: image:loc must never become a page URL.
        fields = {child.tag.rsplit("}", 1)[-1]: child.text for child in entry}
        if fields.get("loc"):
            entries.append((fields["loc"].strip(), fields.get("lastmod")))
    return kind, entries


class BlogCrawler:
    def __init__(self, *, language: str = "ko", delay: float = .5, timeout: float = 30,
                 max_sitemaps: int = 50, max_pages: int = 30,
                 session: requests.Session | None = None):
        if language not in LANGUAGES:
            raise ValueError(f"Unsupported language: {language}")
        self.language = language
        self.config = LANGUAGES[language]
        self.blog = ORIGIN + self.config["blog_path"]
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": AGENT})
        self.session.mount("https://", HTTPAdapter(max_retries=Retry(
            total=2, backoff_factor=.5, status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"], respect_retry_after_header=False,
        )))
        self.delay, self.timeout = delay, timeout
        self.max_sitemaps, self.max_pages = max_sitemaps, max_pages
        self.robots: RobotFileParser | None = None
        self.last_request = 0.0
        self.posts: dict[str, dict] = {}
        self.warnings: list[str] = []
        self.visited_sitemaps: list[str] = []
        self.visited_pages: list[str] = []

    def fetch(self, url: str) -> requests.Response:
        for _ in range(6):
            if not same_origin(url):
                raise ValueError(f"External URL not allowed: {url}")
            if self.robots and not self.robots.can_fetch(AGENT, url):
                raise ValueError(f"Disallowed by robots.txt: {url}")
            time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            response = self.session.get(url, timeout=self.timeout, allow_redirects=False)
            if response.status_code in {301, 302, 303, 307, 308}:
                url = urljoin(url, response.headers["Location"])
                continue
            response.raise_for_status()
            return response
        raise ValueError("Too many redirects")

    def add(self, url: str, *, source: str, title: str = "", lastmod: str | None = None):
        normalized = post_url(url, source, language=self.language)
        if not normalized:
            return
        record = self.posts.setdefault(normalized, {
            "url": normalized, "slug": unquote(urlsplit(normalized).path.split("/")[-1]),
            "title": None, "title_source": None, "last_modified": None, "sources": [],
        })
        if source not in record["sources"]:
            record["sources"].append(source)
        if title:
            record.update(title=title, title_source="blog_link")
        if lastmod:
            record["last_modified"] = lastmod

    def crawl(self) -> list[dict]:
        robots_url = ORIGIN + "/robots.txt"
        try:
            response = self.fetch(robots_url)
            robots_text = response.text
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code != 404:
                raise
            robots_text = "User-agent: *\nAllow: /"
        # Network/permission errors are not treated as permission to crawl.
        self.robots = RobotFileParser(robots_url)
        self.robots.parse(robots_text.splitlines())
        self.delay = max(self.delay, self.robots.crawl_delay(AGENT) or 0)
        declared = self.robots.site_maps() or []
        # Wix advertises per-language indexes. Prefer the selected language index,
        # avoiding unrelated language indexes when possible.
        seeds = [u for u in declared if same_origin(u) and urlsplit(u).path == self.config["sitemap"]]
        seeds = seeds or [u for u in declared if same_origin(u)] or [ORIGIN + "/sitemap.xml"]
        queue, seen = deque(seeds), set()
        while queue:
            url = queue.popleft()
            if url in seen or not same_origin(url):
                continue
            if len(seen) >= self.max_sitemaps:
                self.warnings.append("Sitemap limit reached; collection may be incomplete.")
                break
            seen.add(url)
            try:
                kind, entries = sitemap_entries(self.fetch(url).content)
                self.visited_sitemaps.append(url)
                for location, modified in entries:
                    location = urljoin(url, location)
                    if kind == "sitemapindex":
                        queue.append(location)
                    else:
                        self.add(location, source=url, lastmod=modified)
            except (requests.RequestException, ValueError, ET.ParseError, OSError) as exc:
                self.warnings.append(f"Sitemap failed: {url}: {exc}")
        # Supplement sitemap entries with actual listing links and HTML pagination.
        queue, seen = deque([self.blog]), set()
        while queue:
            url = queue.popleft()
            if url in seen:
                continue
            if len(seen) >= self.max_pages:
                self.warnings.append("Listing-page limit reached; collection may be incomplete.")
                break
            seen.add(url)
            try:
                response = self.fetch(url)
                soup = BeautifulSoup(response.content, "html.parser")
                self.visited_pages.append(url)
                for link in soup.select("a[href]"):
                    target = urljoin(url, link["href"])
                    self.add(target, source=url, title=link.get_text(" ", strip=True))
                    parsed = urlsplit(target)
                    if same_origin(target) and parsed.path.rstrip("/") == self.config["blog_path"]:
                        page = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), parsed.query, ""))
                        if page not in seen:
                            queue.append(page)
            except (requests.RequestException, ValueError) as exc:
                self.warnings.append(f"Listing failed: {url}: {exc}")
        if not self.visited_sitemaps:
            self.warnings.append("No sitemap read successfully; dynamic listing alone may omit posts.")
        return sorted(self.posts.values(), key=lambda p: p["url"])

    def fetch_titles(self, posts: list[dict]) -> None:
        for index, post in enumerate(posts, 1):
            try:
                soup = BeautifulSoup(self.fetch(post["url"]).content, "html.parser")
                heading = soup.select_one("h1")
                og = soup.select_one('meta[property="og:title"]')
                title = heading.get_text(" ", strip=True) if heading else ""
                title = title or (og.get("content", "").strip() if og else "")
                if not title:
                    raise ValueError("No h1 or og:title found")
                post.update(title=title, title_source="article")
            except (requests.RequestException, ValueError) as exc:
                self.warnings.append(f"Title failed: {post['url']}: {exc}")
            if index % 25 == 0 or index == len(posts):
                print(f"Titles: {index}/{len(posts)}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect FeverCoach KO/EN/ES blog post URLs into JSON and TXT.")
    parser.add_argument("--language", choices=LANGUAGES, default="ko")
    parser.add_argument("--output-dir", type=Path, help="Default: outputs/blog_links for KO; outputs/blog_links_en or _es otherwise.")
    parser.add_argument("--fetch-titles", action="store_true", help="Visit each post for its real title (slower).")
    parser.add_argument("--limit", type=int, help="Export at most N links, in URL order (not newest-first).")
    parser.add_argument("--delay", type=float, default=.5, help="Minimum delay between requests in seconds.")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--max-sitemaps", type=int, default=50)
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--overwrite", action="store_true", help="Replace existing output files.")
    args = parser.parse_args()
    if args.output_dir is None:
        args.output_dir = Path("outputs/blog_links" + ("" if args.language == "ko" else f"_{args.language}"))
    if (args.delay < 0 or args.timeout <= 0 or args.max_sitemaps < 1 or args.max_pages < 1
            or (args.limit is not None and args.limit < 1)):
        parser.error("limits and timeout must be positive; delay must be non-negative")
    paths = [args.output_dir / "blog_links.json", args.output_dir / "blog_links.txt"]
    if not args.overwrite and any(p.exists() for p in paths):
        parser.error("Output already exists. Choose another --output-dir or explicitly use --overwrite.")
    crawler = BlogCrawler(language=args.language, delay=args.delay, timeout=args.timeout,
                          max_sitemaps=args.max_sitemaps, max_pages=args.max_pages)
    try:
        posts = crawler.crawl()
    except (requests.RequestException, ValueError) as exc:
        print(f"Crawl failed: {exc}", file=sys.stderr)
        return 1
    found = len(posts)
    if not found:
        print(f"No {args.language.upper()} post links found; no output written.", file=sys.stderr)
        for warning in crawler.warnings:
            print(warning, file=sys.stderr)
        return 1
    if args.limit:
        posts = posts[:args.limit]
    if args.fetch_titles:
        crawler.fetch_titles(posts)
    result = {
        "source": crawler.blog, "language": args.language,
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "partial" if crawler.warnings else "ok",
        "coverage": "Public sitemap and HTML links; not a guarantee of every published post.",
        "total_discovered": found, "exported": len(posts), "limited": len(posts) < found,
        "sitemaps": crawler.visited_sitemaps, "listing_pages": crawler.visited_pages,
        "warnings": crawler.warnings, "posts": posts,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    paths[0].write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths[1].write_text("\n".join(p["url"] for p in posts) + "\n", encoding="utf-8")
    print(f"Discovered {found}; exported {len(posts)}. Status: {result['status']}")
    for path in paths:
        print(path.resolve())
    for warning in crawler.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    return 2 if crawler.warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
