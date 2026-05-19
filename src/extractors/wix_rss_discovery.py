from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET

from src.config.settings import Settings
from src.models import PostRef

from .http import fetch_text


class WixRssDiscovery:
    def __init__(self, settings: Settings):
        self.settings = settings

    def discover(self, source_url: str | None = None, limit: int = 5) -> list[PostRef]:
        rss_url = self.settings.fevercoach_rss_url
        xml_text = fetch_text(rss_url)
        root = ET.fromstring(xml_text)

        posts: list[PostRef] = []
        for item in root.findall("./channel/item"):
            title = _text(item, "title")
            link = _text(item, "link")
            if "/ko/post/" not in link:
                continue

            guid = _text(item, "guid") or hashlib.sha1(link.encode()).hexdigest()
            description = _text(item, "description") or None
            published_at = _text(item, "pubDate") or None
            enclosure = item.find("enclosure")
            thumbnail_url = enclosure.attrib.get("url") if enclosure is not None else None

            posts.append(
                PostRef(
                    id=guid,
                    title=title,
                    url=link,
                    published_at=published_at,
                    thumbnail_url=thumbnail_url,
                    excerpt=description,
                )
            )
            if len(posts) >= limit:
                break

        return posts


def _text(item: ET.Element, tag: str) -> str:
    child = item.find(tag)
    return (child.text or "").strip() if child is not None else ""
