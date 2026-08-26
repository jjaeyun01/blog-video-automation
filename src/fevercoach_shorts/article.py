from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import requests
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class Article:
    title: str
    text: str
    source: str


def load_article(url: str | None = None, file_path: Path | None = None) -> Article:
    if bool(url) == bool(file_path):
        raise ValueError("Provide exactly one of url or file_path.")
    if file_path:
        text = file_path.read_text(encoding="utf-8")
        title = next((line.lstrip("# ").strip() for line in text.splitlines() if line.strip()), file_path.stem)
        return Article(title=title, text=_clean(text), source=str(file_path.resolve()))

    response = requests.get(
        str(url),
        timeout=30,
        headers={"User-Agent": "FeverCoachShorts/0.1 (+https://www.fevercoach.us)"},
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for node in soup.select("script, style, nav, footer, header, noscript"):
        node.decompose()
    title_node = soup.select_one("h1") or soup.select_one("title")
    title = title_node.get_text(" ", strip=True) if title_node else "FeverCoach article"
    article_node = soup.select_one("article") or soup.select_one("main") or soup.body
    text = article_node.get_text("\n", strip=True) if article_node else soup.get_text("\n", strip=True)
    return Article(title=title, text=_clean(text), source=str(url))


def _clean(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
