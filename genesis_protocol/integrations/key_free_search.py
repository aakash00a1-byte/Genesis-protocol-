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

        providers = [("duckduckgo", self._search_duckduckgo)]
        if any(hint in query.lower() for hint in _NEWS_HINTS):
            providers.append(("google_news", self._search_google_news))
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

        items = re.findall(
            r"<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>"
            r".*?<pubDate>(.*?)</pubDate>",
            response.text,
            re.S,
        )
        return [
            {"title": _strip_tags(t), "url": l.strip(),
             "content": f"Published {_strip_tags(p)}"}
            for t, l, p in items[:max_results]
        ]

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
