from __future__ import annotations

import hashlib
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

from src.models import Article, PostRef

from .http import fetch_text


class ArticleExtractor:
    def extract(self, post: PostRef) -> Article:
        html = fetch_text(post.url)
        title = _extract_title(html) or post.title
        body_text = _html_to_text(html)

        return Article(
            id=post.id,
            url=post.url,
            title=title,
            raw_text=body_text,
            published_at=post.published_at,
            thumbnail_url=post.thumbnail_url,
            excerpt=post.excerpt,
            language=post.language,
        )

    def extract_file(self, path: Path) -> Article:
        raw_text = path.read_text(encoding="utf-8")
        title = _first_non_empty_line(raw_text) or path.stem
        article_id = hashlib.sha1(str(path.resolve()).encode()).hexdigest()[:12]
        return Article(
            id=article_id,
            url=str(path.resolve()),
            title=title,
            raw_text=raw_text,
        )


class _TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag in {"p", "div", "li", "h1", "h2", "h3", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag in {"p", "div", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            text = data.strip()
            if text:
                self.parts.append(text)


def _html_to_text(html: str) -> str:
    parser = _TextHTMLParser()
    parser.feed(html)
    text = unescape(" ".join(parser.parts))
    return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def _extract_title(html: str) -> str | None:
    og_match = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    if og_match:
        return unescape(og_match.group(1)).strip()
    title_match = re.search(r"<title>(.*?)</title>", html, flags=re.DOTALL | re.IGNORECASE)
    if title_match:
        return unescape(title_match.group(1)).strip()
    return None


def _first_non_empty_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None
