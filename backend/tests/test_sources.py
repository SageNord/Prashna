from email.message import Message
from urllib.error import URLError

import pytest

from app.services import sources
from app.services.ingestion import _safe_source_error
from app.services.sources import FeedSource, configured_sources, fetch_feed


PIB_PRESS_RELEASES_URL = "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=1"

PIB_RSS_RESPONSE = b'''<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Press Information Bureau</title>
    <item>
      <title>Government announces new biodiversity conservation measures</title>
      <link>https://pib.gov.in/PressReleasePage.aspx?PRID=1234567</link>
      <guid isPermaLink="false">PIB-1234567</guid>
      <pubDate>Tue, 29 Sep 2026 10:30:00 +0530</pubDate>
      <description><![CDATA[Short release description.]]></description>
      <content:encoded><![CDATA[<p>New conservation measures support wildlife and biodiversity.</p>]]></content:encoded>
    </item>
  </channel>
</rss>'''


class FakeResponse:
    def __init__(self, payload: bytes, content_type: str = "text/xml"):
        self.payload = payload
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size: int = -1) -> bytes:
        return self.payload


def test_default_pib_source_is_the_official_press_releases_endpoint(monkeypatch):
    monkeypatch.delenv("NEWS_RSS_FEEDS", raising=False)
    pib = next(source for source in configured_sources() if source.name == "Press Information Bureau")
    assert pib.url == PIB_PRESS_RELEASES_URL
    assert "ViewRss.aspx" not in pib.url


def test_pib_rss_response_parses_text_xml_and_namespaced_content(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["user_agent"] = request.get_header("User-agent")
        captured["accept"] = request.get_header("Accept")
        captured["timeout"] = timeout
        return FakeResponse(PIB_RSS_RESPONSE)

    monkeypatch.setattr(sources, "urlopen", fake_urlopen)
    monkeypatch.setattr(sources.time, "sleep", lambda _seconds: None)
    source = FeedSource("Press Information Bureau", PIB_PRESS_RELEASES_URL, 100)

    items = fetch_feed(source, limit=10)

    assert len(items) == 1
    assert items[0].title == "Government announces new biodiversity conservation measures"
    assert items[0].url == "https://pib.gov.in/PressReleasePage.aspx?PRID=1234567"
    assert items[0].source_identifier == "PIB-1234567"
    assert items[0].summary == "New conservation measures support wildlife and biodiversity."
    assert items[0].published_at.isoformat() == "2026-09-29T05:00:00"
    assert captured["url"] == PIB_PRESS_RELEASES_URL
    assert captured["user_agent"].startswith("Mozilla/5.0")
    assert "text/xml" in captured["accept"]


def test_transport_error_has_safe_actionable_reason_and_bounded_retries(monkeypatch):
    attempts = 0

    def failing_urlopen(_request, timeout):
        nonlocal attempts
        attempts += 1
        raise URLError("timed out")

    monkeypatch.setattr(sources, "urlopen", failing_urlopen)
    monkeypatch.setattr(sources.time, "sleep", lambda _seconds: None)
    source = FeedSource("Press Information Bureau", PIB_PRESS_RELEASES_URL, 100)

    with pytest.raises(RuntimeError, match="request timed out") as error:
        fetch_feed(source)

    assert attempts == 3
    assert "https://" not in str(error.value)


def test_source_error_logging_redacts_urls_and_credential_values():
    detail = _safe_source_error(RuntimeError(
        "request failed at https://feeds.example/rss?token=top-secret api_key=also-secret"
    ))
    assert "feeds.example" not in detail
    assert "top-secret" not in detail
    assert "also-secret" not in detail
    assert "[redacted]" in detail
