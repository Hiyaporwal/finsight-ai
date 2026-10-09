"""Fetches recent headlines from Google News RSS. Returns only what the feed contains."""
import logging
import re
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import requests
from defusedxml import ElementTree as ET

log = logging.getLogger(__name__)

# Terms used to decide whether a headline is about the company (case-insensitive, whole words)
ALIASES = {
    "RELIANCE.NS": ["Reliance Industries", "Reliance"],
    "TCS.NS": ["Tata Consultancy Services", "TCS"],
    "HDFCBANK.NS": ["HDFC Bank"],
    "ICICIBANK.NS": ["ICICI Bank"],
    "INFY.NS": ["Infosys"],
    "SBIN.NS": ["State Bank of India", "SBI"],
    "LT.NS": ["Larsen & Toubro", "Larsen and Toubro", "L&T"],
    "TMPV.NS": ["Tata Motors"],
    "BHARTIARTL.NS": ["Bharti Airtel", "Airtel"],
    "ITC.NS": ["ITC"],
}
SEARCH_TERM = {s: a[0] for s, a in ALIASES.items()}


class NewsError(Exception):
    pass


def parse_rss(xml_text: str) -> list:
    try:
        root = ET.fromstring(xml_text)
    except Exception as exc:
        raise NewsError(f"Could not parse the news feed: {exc}")
    items, seen = [], set()
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        source = (it.findtext("source") or "").strip()
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3].strip()
        if not title or title.lower() in seen:
            continue
        seen.add(title.lower())
        published = None
        raw = it.findtext("pubDate")
        if raw:
            try:
                published = parsedate_to_datetime(raw).astimezone(timezone.utc)
            except Exception:
                published = None
        items.append({"title": title, "link": link, "source": source or "Unknown",
                      "published": published.isoformat() if published else None})
    return items


def matches_company(title: str, aliases: list) -> bool:
    for a in aliases:
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(a) + r"(?![A-Za-z0-9])", title, re.IGNORECASE):
            return True
    return False


class GoogleNewsProvider:
    name = "Google News RSS"

    def __init__(self, retries=2, timeout=10):
        self.retries, self.timeout = retries, timeout

    def fetch(self, symbol: str) -> list:
        term = SEARCH_TERM.get(symbol)
        if not term:
            raise NewsError("No search term configured for this symbol")
        q = quote_plus(f'"{term}" stock when:30d')
        url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
        last = None
        for attempt in range(1, self.retries + 1):
            try:
                r = requests.get(url, timeout=self.timeout, headers={"User-Agent": "Mozilla/5.0 FinSightAI"})
                r.raise_for_status()
                items = parse_rss(r.text)
                return [i for i in items if matches_company(i["title"], ALIASES[symbol])]
            except Exception as exc:
                last = exc
                log.warning("news %s attempt %d/%d failed: %s", symbol, attempt, self.retries, exc)
                time.sleep(1.5 ** attempt)
        raise NewsError(f"Could not load news: {last}")


class NewsService:
    def __init__(self, provider, ttl=900, error_ttl=60):
        self.provider, self.ttl, self.error_ttl = provider, ttl, error_ttl
        self._cache, self._lock = {}, threading.Lock()

    def get(self, symbol: str) -> dict:
        with self._lock:
            hit = self._cache.get(symbol)
            if hit and time.time() - hit[0] < (self.ttl if hit[1].get("items") is not None else self.error_ttl):
                return hit[1]
        fetched = datetime.now(timezone.utc).isoformat()
        try:
            res = {"items": self.provider.fetch(symbol), "fetched_at": fetched, "source": self.provider.name}
        except NewsError as exc:
            res = {"items": None, "error": str(exc), "fetched_at": fetched}
        with self._lock:
            self._cache[symbol] = (time.time(), res)
        return res


news_service = NewsService(GoogleNewsProvider())