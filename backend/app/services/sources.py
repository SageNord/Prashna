"""Fetch permitted RSS/Atom feeds without scraping publisher article pages."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from .relevance import utc_naive

log = logging.getLogger(__name__)
MAX_FEED_BYTES = 2_000_000
DEFAULT_FEEDS = (
    ("Press Information Bureau", "https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=1", 100),
    ("Reserve Bank of India", "https://rbi.org.in/pressreleases_rss.xml", 95),
)


@dataclass(frozen=True)
class FeedSource:
    name: str
    url: str
    priority: int = 50


@dataclass(frozen=True)
class RawArticle:
    title: str
    url: str
    source: str
    source_identifier: str | None
    published_at: datetime | None
    summary: str


class _TextOnly(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def strip_html(value: str) -> str:
    parser = _TextOnly()
    try:
        parser.feed(value)
        return " ".join(" ".join(parser.parts).split())
    except Exception:
        return " ".join(value.split())


def canonicalize_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme.lower() != "https" or not parts.hostname:
        raise ValueError("Source article URLs must use HTTPS and include a hostname")
    host = parts.hostname.lower()
    if parts.port and parts.port != 443:
        host = f"{host}:{parts.port}"
    query = [(key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid", "ref", "source"}]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, urlencode(sorted(query)), ""))


def configured_sources() -> list[FeedSource]:
    raw = os.getenv("NEWS_RSS_FEEDS", "").strip()
    if not raw:
        return [FeedSource(*item) for item in DEFAULT_FEEDS]
    sources: list[FeedSource] = []
    for item in raw.split(";"):
        fields = item.strip().split("|")
        if len(fields) not in (2, 3) or not fields[0].strip():
            raise ValueError("NEWS_RSS_FEEDS entries must be Source Name|https://feed-url[|priority]")
        url = fields[1].strip()
        if not url.startswith("https://"):
            raise ValueError("Configured RSS feeds must use HTTPS")
        priority = int(fields[2]) if len(fields) == 3 else 50
        sources.append(FeedSource(fields[0].strip()[:200], url, max(0, min(priority, 100))))
    return sources


def fetch_feed(source: FeedSource, timeout: float = 12.0, limit: int = 40) -> list[RawArticle]:
    if not source.url.startswith("https://"):
        raise ValueError("RSS feeds must use HTTPS")
    request = Request(source.url, headers={"User-Agent": "PrashnaCurrentAffairs/1.0 (+https://prashna-xi.vercel.app)", "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"})
    try:
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"application/rss+xml", "application/atom+xml", "application/xml", "text/xml", "application/octet-stream"}:
                raise ValueError(f"Unexpected RSS content type: {content_type}")
            payload = response.read(MAX_FEED_BYTES + 1)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"RSS fetch failed for {source.name}: {type(exc).__name__}") from exc
    if len(payload) > MAX_FEED_BYTES:
        raise ValueError(f"RSS feed exceeded the {MAX_FEED_BYTES} byte limit")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError(f"Malformed RSS/XML from {source.name}") from exc
    items = [node for node in root.iter() if _local_name(node.tag) in {"item", "entry"}]
    articles: list[RawArticle] = []
    for item in items[:limit]:
        fields = {_local_name(child.tag): child for child in item}
        title = _node_text(fields.get("title"))
        if not title:
            continue
        link_node = fields.get("link")
        link = _node_text(link_node)
        if link_node is not None and not link:
            link = link_node.attrib.get("href", "")
        identifier = _node_text(fields.get("guid") or fields.get("id")) or None
        if not link and identifier and identifier.startswith("https://"):
            link = identifier
        try:
            canonical = canonicalize_url(link)
        except ValueError:
            # Invalid/non-HTTPS source links are not safe to publish or fetch.
            continue
        published = _parse_datetime(_node_text(fields.get("pubDate") or fields.get("published") or fields.get("updated") or fields.get("date")))
        summary = strip_html(_node_text(fields.get("encoded") or fields.get("description") or fields.get("summary") or fields.get("content")))[:12000]
        articles.append(RawArticle(title=title[:300], url=canonical, source=source.name,
                                   source_identifier=(identifier or canonical)[:1000],
                                   published_at=utc_naive(published), summary=summary))
    return articles


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1].lower()


def _node_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split()).strip()


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        result = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError):
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)
