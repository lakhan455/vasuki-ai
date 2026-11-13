from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import aiohttp
from bs4 import BeautifulSoup

from app.config import Settings

PROFILE_FEEDS = {
    "general": (
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
    ),
    "movies": (
        "https://variety.com/feed/",
        "https://deadline.com/feed/",
        "https://www.hollywoodreporter.com/feed/",
    ),
    "technology": (
        "https://github.blog/feed/",
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://feeds.arstechnica.com/arstechnica/index",
    ),
    "finance": ("https://feeds.bbci.co.uk/news/business/rss.xml",),
    "sports": ("https://feeds.bbci.co.uk/sport/rss.xml",),
}

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "new", "latest",
    "current", "mujhe", "batao", "bata", "kya", "hai", "he", "2026",
}
NOISE = re.compile(
    r"cookie|consent|advert|promo|newsletter|subscribe|social-share|related|"
    r"recommended|menu|navigation|breadcrumb|sidebar|modal|popup|paywall",
    re.I,
)
ROBOTS_CACHE: dict[str, tuple[float, RobotFileParser | None]] = {}
ROBOTS_TTL = 1800.0

@dataclass(slots=True)
class FeedEntry:
    title: str
    url: str
    summary: str = ""
    published_date: str = ""
    score: float = 0.0


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _terms(query: str) -> set[str]:
    return {
        x for x in re.findall(r"[\w-]+", str(query or "").casefold())
        if len(x) >= 3 and x not in STOPWORDS
    }


def _obviously_private_host(host: str) -> bool:
    value = str(host or "").strip().casefold().rstrip(".")
    if not value or value in {"localhost", "localhost.localdomain"}:
        return True
    if value.endswith((".local", ".internal")):
        return True
    try:
        return not ipaddress.ip_address(value).is_global
    except ValueError:
        return False


async def _public_url(url: str) -> bool:
    try:
        parsed = urlparse(str(url or "").strip())
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.username or parsed.password or _obviously_private_host(parsed.hostname):
        return False
    try:
        rows = await asyncio.to_thread(
            socket.getaddrinfo,
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError:
        return False
    ips = {str(row[4][0]) for row in rows if row[4]}
    if not ips:
        return False
    try:
        return all(ipaddress.ip_address(ip).is_global for ip in ips)
    except ValueError:
        return False


def _html_to_text(html: str, max_chars: int) -> str:
    soup = BeautifulSoup(str(html or ""), "html.parser")
    for node in soup.select(
        "script,style,noscript,svg,canvas,nav,footer,header,aside,form,button,dialog"
    ):
        node.decompose()
    for node in list(soup.find_all(True)):
        identity = " ".join([
            str(node.get("id") or ""),
            " ".join(node.get("class") or []),
            str(node.get("role") or ""),
        ])
        if NOISE.search(identity):
            node.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    rows, seen = [], set()
    for node in root.find_all(["h1", "h2", "h3", "p", "li", "blockquote"]):
        value = _clean(node.get_text(" ", strip=True))
        if len(value) < 30 or value.casefold() in seen:
            continue
        seen.add(value.casefold())
        rows.append(value)
    text = "\n".join(rows) if rows else _clean(root.get_text(" ", strip=True))
    return text[:max_chars]


def _date(value: str) -> str:
    raw = _clean(value)
    if not raw:
        return ""
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return raw[:100]


def _node_text(node, names):
    for child in node.iter():
        if child.tag.rsplit("}", 1)[-1].casefold() in names:
            value = _clean("".join(child.itertext()))
            if value:
                return value
    return ""


def _link(node):
    direct = _clean(node.findtext("link") or "")
    if direct:
        return direct
    for child in node.iter():
        if child.tag.rsplit("}", 1)[-1].casefold() == "link":
            href = _clean(child.attrib.get("href") or "")
            rel = _clean(child.attrib.get("rel") or "")
            if href and rel in {"", "alternate"}:
                return href
    return ""


def _parse_feed(xml_text: str, base_url: str = "") -> list[FeedEntry]:
    try:
        root = ET.fromstring(str(xml_text or ""))
    except ET.ParseError:
        return []
    out = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1].casefold() not in {"item", "entry"}:
            continue
        title = _node_text(node, {"title"})
        link = _link(node)
        if link and base_url:
            link = urljoin(base_url, link)
        summary = _node_text(node, {"description", "summary", "content", "encoded"})
        if "<" in summary and ">" in summary:
            summary = _html_to_text(summary, 2400)
        published = _node_text(node, {"pubdate", "published", "updated", "date"})
        if title and link:
            out.append(FeedEntry(title[:500], link[:3000], summary[:3000], _date(published)))
        if len(out) >= 80:
            break
    return out


def _relevance_score(query: str, title: str, summary: str, published_date: str = "") -> float:
    terms = _terms(query)
    title_l, summary_l = title.casefold(), summary.casefold()
    score = sum(3.0 for x in terms if x in title_l) + sum(1.0 for x in terms if x in summary_l)
    if terms and score == 0:
        return 0.0
    if published_date:
        try:
            dt = datetime.fromisoformat(published_date.replace("Z", "+00:00"))
            age = max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600)
            score += 1.5 if age <= 24 else 0.8 if age <= 168 else 0.3 if age <= 720 else 0.0
        except Exception:
            pass
    return round(score, 4)


def _feeds(settings: Settings, profile_key: str | None) -> list[str]:
    rows = list(PROFILE_FEEDS["general"])
    if profile_key in PROFILE_FEEDS:
        rows.extend(PROFILE_FEEDS[profile_key])
    rows.extend(x.strip() for x in re.split(r"[\n,]+", str(settings.crawler_rss_feeds or "")) if x.strip())
    limit = max(1, min(40, int(settings.crawler_max_feed_sources)))
    return list(dict.fromkeys(rows))[:limit]


class AsyncWebCrawler:
    def __init__(self, settings: Settings):
        self.s = settings
        self.timeout = max(1.0, min(20.0, float(settings.crawler_timeout_seconds)))
        self.total = max(self.timeout, min(30.0, float(settings.crawler_total_budget_seconds)))
        self.concurrency = max(2, min(40, int(settings.crawler_concurrency)))
        self.per_host = max(1, min(6, int(settings.crawler_per_host_concurrency)))
        self.max_bytes = max(100000, min(5000000, int(settings.crawler_max_bytes)))
        self.max_chars = max(1000, min(20000, int(settings.crawler_max_content_chars)))
        self.user_agent = str(settings.crawler_user_agent or "VasukiAI-Crawler/1.0")[:300]

    async def _robots(self, session, url):
        if not self.s.crawler_respect_robots:
            return True
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        cached = ROBOTS_CACHE.get(origin)
        now = time.monotonic()
        if cached and now - cached[0] < ROBOTS_TTL:
            return True if cached[1] is None else cached[1].can_fetch(self.user_agent, url)
        parser = None
        try:
            async with session.get(origin + "/robots.txt", allow_redirects=True) as resp:
                if resp.status < 400:
                    parser = RobotFileParser()
                    parser.parse((await resp.text(errors="ignore")).splitlines())
        except Exception:
            parser = None
        ROBOTS_CACHE[origin] = (now, parser)
        return True if parser is None else parser.can_fetch(self.user_agent, url)

    async def _fetch(self, session, url, robots=True):
        if not await _public_url(url):
            return "", ""
        if robots and not await self._robots(session, url):
            return "", ""
        try:
            async with session.get(url, allow_redirects=True, max_redirects=5) as resp:
                if resp.status >= 400:
                    return "", ""
                final = str(resp.url)
                if not await _public_url(final):
                    return "", ""
                ctype = str(resp.headers.get("Content-Type", "")).casefold()
                if ctype and not any(x in ctype for x in ("text/", "xml", "rss", "atom")):
                    return "", ""
                raw = await resp.content.read(self.max_bytes + 1)
                if len(raw) > self.max_bytes:
                    return "", ""
                enc = resp.charset or "utf-8"
                try:
                    return raw.decode(enc, errors="ignore"), final
                except LookupError:
                    return raw.decode("utf-8", errors="ignore"), final
        except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeError):
            return "", ""

    async def search(self, query: str, max_results: int = 8, profile_key: str | None = None) -> list[dict]:
        if not self.s.crawler_enabled:
            return []
        timeout = aiohttp.ClientTimeout(total=self.timeout, connect=min(3.0, self.timeout), sock_read=self.timeout)
        connector = aiohttp.TCPConnector(limit=self.concurrency, limit_per_host=self.per_host, ttl_dns_cache=300)
        headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/xml,text/xml,application/rss+xml,application/atom+xml,*/*;q=0.5"}
        async with aiohttp.ClientSession(timeout=timeout, connector=connector, headers=headers) as session:
            async def feed_job(url):
                text, final = await self._fetch(session, url, robots=False)
                return _parse_feed(text, final or url)
            try:
                batches = await asyncio.wait_for(
                    asyncio.gather(*(feed_job(url) for url in _feeds(self.s, profile_key)), return_exceptions=True),
                    timeout=self.total,
                )
            except asyncio.TimeoutError:
                return []
            entries = []
            for batch in batches:
                if not isinstance(batch, Exception):
                    entries.extend(batch)
            unique = {}
            for item in entries:
                item.score = _relevance_score(query, item.title, item.summary, item.published_date)
                if item.score > 0 and (item.url not in unique or item.score > unique[item.url].score):
                    unique[item.url] = item
            ranked = sorted(unique.values(), key=lambda x: (x.score, x.published_date), reverse=True)
            selected = ranked[: max(1, min(30, int(self.s.crawler_max_pages)))]

            async def article_job(item):
                html, final = await self._fetch(session, item.url, robots=True)
                content = _html_to_text(html, self.max_chars) if html else ""
                if len(content) < 120:
                    content = _html_to_text(item.summary, self.max_chars)
                if len(content) < 80:
                    return None
                url = final or item.url
                return {
                    "title": item.title,
                    "url": url,
                    "domain": urlparse(url).netloc.casefold().removeprefix("www."),
                    "content": content[: self.max_chars],
                    "score": item.score,
                    "published_date": item.published_date,
                    "crawler_source": "rss+direct-page",
                }
            try:
                pages = await asyncio.wait_for(
                    asyncio.gather(*(article_job(item) for item in selected), return_exceptions=True),
                    timeout=max(1.0, self.total - self.timeout),
                )
            except asyncio.TimeoutError:
                pages = []
        out, seen = [], set()
        for item in pages:
            if isinstance(item, dict) and item.get("url") and item["url"] not in seen:
                seen.add(item["url"])
                out.append(item)
        return out[: max(1, max_results)]


async def crawl_live_web(query: str, settings: Settings, max_results: int = 8, *, profile_key: str | None = None) -> list[dict]:
    return await AsyncWebCrawler(settings).search(query, max_results=max_results, profile_key=profile_key)
