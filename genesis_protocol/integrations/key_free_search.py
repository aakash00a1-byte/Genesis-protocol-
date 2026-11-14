"""Key-free web search.

Used when Tavily is unset or fails, so a live lookup still returns real data
instead of nothing. Providers are tried in order and each is independent, so a
host blocked from one deployment does not stop the others:

1. DuckDuckGo HTML endpoint (general web results).
2. Google News RSS (headlines for news-shaped queries).
3. Wikipedia search API (encyclopaedic facts).

This is a best-effort reader, not a guaranteed index. It never invents a
result: if every provider fails it returns an error, and the caller reports the
failure honestly rather than filling the gap with a guess.
"""

import html
import re
from typing import Any, Dict, List
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from genesis_protocol.utils.logger import get_logger

logger = get_logger("integrations.key_free_search")

_UA = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
_TIMEOUT = 12.0

_NEWS_HINTS = (
    "news", "headline", "khabar", "latest", "breaking", "today",
    "current", "recent", "update", "score", "price", "rate",
)


def _strip_tags(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def _decode_ddg_url(href: str) -> str:
    """DuckDuckGo wraps links as /l/?uddg=<encoded>. Unwrap them."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg")
        if target:
            return unquote(target[0])
    return href


class KeyFreeSearch:
    """Search the web without an API key."""

    def __init__(self):
        self._client = httpx.AsyncClient(
            timeout=_TIMEOUT, follow_redirects=True, headers=_UA
        )

    async def search(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Try each provider in order; return the first with results."""
        errors: List[str] = []

        is_news = any(hint in query.lower() for hint in _NEWS_HINTS)
        if is_news:
            # Google News returns real headlines attributed to a publisher;
            # DuckDuckGo mostly returns aggregator landing pages for news.
            providers = [("google_news", self._search_google_news),
                         ("duckduckgo", self._search_duckduckgo)]
        else:
            providers = [("duckduckgo", self._search_duckduckgo)]
        providers.append(("wikipedia", self._search_wikipedia))

        for name, provider in providers:
            try:
                results = await provider(query, max_results)
                if results:
                    logger.info(f"key-free search via {name}", query=query,
                                results=len(results))
                    return {"results": results, "source": name}
                errors.append(f"{name}: no results")
            except Exception as e:
                logger.warning(f"key-free provider {name} failed: {e}")
                errors.append(f"{name}: {e}")

        return {"error": "; ".join(errors) or "no provider returned results",
                "results": []}

    async def _search_duckduckgo(self, query: str, max_results: int) -> List[Dict]:
        response = await self._client.post(
            "https://html.duckduckgo.com/html/", data={"q": query}
        )
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")

        blocks = re.findall(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
            r'(.*?)(?=<a[^>]+class="result__a"|</div>\s*</div>\s*</div>)',
            response.text,
            re.S,
        )
        results = []
        for href, title, rest in blocks:
            snippet_match = re.search(
                r'class="result__snippet"[^>]*>(.*?)</a>', rest, re.S
            )
            results.append({
                "title": _strip_tags(title),
                "url": _decode_ddg_url(href),
                "content": _strip_tags(snippet_match.group(1)) if snippet_match else "",
            })
            if len(results) >= max_results:
                break
        return results

    async def _search_google_news(self, query: str, max_results: int) -> List[Dict]:
        response = await self._client.get(
            "https://news.google.com/rss/search",
            params={"q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"},
        )
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")

        items = re.findall(r"<item>(.*?)</item>", response.text, re.S)
        results = []
        for item in items[:max_results]:
            title_m = re.search(r"<title>(.*?)</title>", item, re.S)
            link_m = re.search(r"<link>(.*?)</link>", item, re.S)
            date_m = re.search(r"<pubDate>(.*?)</pubDate>", item, re.S)
            src_m = re.search(
                r"<source[^>]*url=\"([^\"]*)\"[^>]*>(.*?)</source>", item, re.S
            )
            if not (title_m and link_m):
                continue

            title = _strip_tags(title_m.group(1))
            publisher = _strip_tags(src_m.group(2)) if src_m else None
            if publisher and title.endswith(f" - {publisher}"):
                title = title[: -len(f" - {publisher}")].strip()
            if not publisher and " - " in title:
                head, _, tail = title.rpartition(" - ")
                if head and len(tail) <= 40:
                    title, publisher = head, tail

            entry = {
                "title": title,
                "url": link_m.group(1).strip(),
                "published": _strip_tags(date_m.group(1)) if date_m else "",
            }
            if publisher:
                entry["publisher"] = publisher
            # The <source url> is the publisher's own site, an authoritative
            # attribution. The Google News link is a JS redirect, so the real
            # article URL cannot be recovered; we give the publisher domain and
            # the Google News link rather than inventing a deep link.
            if src_m and src_m.group(1):
                entry["publisher_url"] = src_m.group(1).strip()
            entry["content"] = f"Published {entry['published']}"
            results.append(entry)
        return results

    async def _search_wikipedia(self, query: str, max_results: int) -> List[Dict]:
        response = await self._client.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query", "list": "search", "srsearch": query,
                "format": "json", "srlimit": max_results,
            },
        )
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")

        hits = response.json().get("query", {}).get("search", [])
        return [
            {
                "title": h.get("title", ""),
                "url": "https://en.wikipedia.org/wiki/" + h.get("title", "").replace(" ", "_"),
                "content": _strip_tags(h.get("snippet", "")),
            }
            for h in hits[:max_results]
        ]

    async def close(self):
        await self._client.aclose()


_instance: KeyFreeSearch = None


def get_key_free_search() -> KeyFreeSearch:
    global _instance
    if _instance is None:
        _instance = KeyFreeSearch()
    return _instance
