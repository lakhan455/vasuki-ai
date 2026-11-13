from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services import research
from app.services.web_crawler import (
    _html_to_text,
    _obviously_private_host,
    _parse_feed,
    _relevance_score,
)


def test_crawler_strips_noise():
    html = """
    <html><body>
    <nav>REMOVE MENU</nav>
    <div class='cookie-consent'>REMOVE COOKIES</div>
    <article>
      <h1>Vasuki AI launches new search engine</h1>
      <p>This useful article paragraph should remain after extraction.</p>
      <p>The crawler keeps meaningful evidence text for the AI.</p>
    </article>
    <script>alert('remove')</script>
    </body></html>
    """
    text = _html_to_text(html, 5000)
    assert "useful article" in text
    assert "meaningful evidence" in text
    assert "REMOVE MENU" not in text
    assert "REMOVE COOKIES" not in text
    assert "alert" not in text


def test_crawler_parses_rss():
    xml = """
    <rss><channel><item>
      <title>New movie announced for 2026</title>
      <link>https://example.com/movie</link>
      <description>Fresh movie release information.</description>
      <pubDate>Fri, 13 Nov 2026 10:00:00 GMT</pubDate>
    </item></channel></rss>
    """
    rows = _parse_feed(xml)
    assert len(rows) == 1
    assert rows[0].url == "https://example.com/movie"
    assert "2026" in rows[0].published_date


def test_relevance_rejects_unrelated_article():
    good = _relevance_score("2026 movie release", "Major movie release announced", "Studio confirms 2026 release")
    bad = _relevance_score("2026 movie release", "Weather update", "Rain expected tomorrow")
    assert good > 0
    assert bad == 0


def test_private_targets_rejected():
    assert _obviously_private_host("localhost") is True
    assert _obviously_private_host("127.0.0.1") is True
    assert _obviously_private_host("10.0.0.1") is True
    assert _obviously_private_host("192.168.1.10") is True
    assert _obviously_private_host("8.8.8.8") is False


def test_research_uses_crawler_when_apis_empty(monkeypatch):
    async def empty(*args, **kwargs):
        return []
    async def crawler(query, settings, max_results=8, *, profile_key=None):
        return [{
            "title": "Studio announces 2026 film",
            "url": "https://variety.com/example-film",
            "domain": "variety.com",
            "content": "The studio announced a new film for release in 2026 with confirmed production details.",
            "score": 8.0,
            "published_date": "2026-11-13T10:00:00+00:00",
        }]
    monkeypatch.setattr(research, "tavily_search", empty)
    monkeypatch.setattr(research, "exa_search", empty)
    monkeypatch.setattr(research, "crawl_live_web", crawler)
    settings = SimpleNamespace(tavily_api_key=None, exa_api=None, crawler_enabled=True)
    rows, provider = asyncio.run(research.search_web(
        "2026 ki new movie batao",
        settings,
        max_results=5,
        require_current=True,
        as_of="2026-11-13",
    ))
    assert rows
    assert rows[0]["domain"] == "variety.com"
    assert "crawler" in provider
