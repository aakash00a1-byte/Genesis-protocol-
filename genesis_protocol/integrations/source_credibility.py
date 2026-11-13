"""Source credibility labels for live news.

Finding a headline is not the same as confirming it. A press release hosted on
a wire service is not independent reporting, and a single unknown blog is not
the same as Reuters. This module labels each result so the agent can say how
much a claim is actually worth instead of presenting everything as fact:

- ``verified``               - a recognised news organisation reported it.
- ``developing``             - a single or lesser-known source only.
- ``promotional-unverified`` - a press release, sponsored or self-reported item.

The labels are deliberately conservative: unknown is treated as unverified, not
as trusted.
"""

from typing import Any, Dict, List
from urllib.parse import urlparse

# Recognised news organisations. Not exhaustive, but these are the ones that
# appear in general search results and carry editorial responsibility.
TRUSTED_NEWS_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "theguardian.com",
    "nytimes.com", "washingtonpost.com", "economist.com", "ft.com",
    "bloomberg.com", "cnbc.com", "wsj.com", "forbes.com", "cnn.com",
    "thehindu.com", "indianexpress.com", "timesofindia.indiatimes.com",
    "hindustantimes.com", "livemint.com", "business-standard.com",
    "economictimes.indiatimes.com", "ndtv.com", "thewire.in", "scroll.in",
    "aljazeera.com", "npr.org", "abc.net.au", "dw.com", "nature.com",
    "science.org", "techcrunch.com", "arstechnica.com", "wired.com",
    "theverge.com", "zdnet.com", "venturebeat.com", "theinformation.com",
}

# Wire services whose content is normally paid/self-submitted, i.e. promotional
# unless a newsroom has picked it up separately.
PRESS_RELEASE_DOMAINS = {
    "globenewswire.com", "prnewswire.com", "businesswire.com", "accesswire.com",
    "einpresswire.com", "prlog.org", "openpr.com", "newsfilecorp.com",
    "pressreleasepoint.com", "issuewire.com", "send2press.com",
}

# Words that mark content as paid or self-promotional.
PROMOTIONAL_MARKERS = (
    "sponsored", "press release", "prnewswire", "paid post", "advertorial",
    "promoted content", "partner content", "brand post", "self-reported",
)

LABEL_VERIFIED = "verified"
LABEL_DEVELOPING = "developing"
LABEL_PROMOTIONAL = "promotional-unverified"


# Publisher names as they appear in Google News titles, mapped to their domain.
# Google News links point at news.google.com, so the title's "- Publisher" suffix
# is the real attribution.
PUBLISHER_TO_DOMAIN = {
    "reuters": "reuters.com", "the associated press": "apnews.com",
    "ap": "apnews.com", "bbc news": "bbc.com", "bbc": "bbc.com",
    "the guardian": "theguardian.com", "the new york times": "nytimes.com",
    "the washington post": "washingtonpost.com", "the economist": "economist.com",
    "financial times": "ft.com", "bloomberg": "bloomberg.com",
    "cnbc": "cnbc.com", "the wall street journal": "wsj.com", "wsj": "wsj.com",
    "forbes": "forbes.com", "cnn": "cnn.com", "the hindu": "thehindu.com",
    "the indian express": "indianexpress.com",
    "the times of india": "timesofindia.indiatimes.com",
    "hindustan times": "hindustantimes.com", "livemint": "livemint.com",
    "mint": "livemint.com", "business standard": "business-standard.com",
    "the economic times": "economictimes.indiatimes.com", "ndtv": "ndtv.com",
    "al jazeera": "aljazeera.com", "al jazeera english": "aljazeera.com",
    "npr": "npr.org", "abc news": "abc.net.au", "deutsche welle": "dw.com",
    "nature": "nature.com", "science": "science.org",
    "techcrunch": "techcrunch.com", "ars technica": "arstechnica.com",
    "wired": "wired.com", "the verge": "theverge.com", "zdnet": "zdnet.com",
    "venturebeat": "venturebeat.com", "india today": "indiatoday.in",
    "the telegraph": "telegraph.co.uk", "the sun": "thesun.co.uk",
    "sciencedaily": "sciencedaily.com", "axios": "axios.com",
    "politico": "politico.com", "the register": "theregister.com",
    "engadget": "engadget.com", "gizmodo": "gizmodo.com",
}


def _domain(url: str) -> str:
    netloc = urlparse(url or "").netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _is_trusted(domain: str) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in TRUSTED_NEWS_DOMAINS)


def _is_press_release(domain: str) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in PRESS_RELEASE_DOMAINS)


def classify(title: str, url: str, content: str = "",
             publisher: str = "") -> Dict[str, Any]:
    """Label one search result.

    ``publisher`` is the attribution Google News adds ("Headline - Publisher").
    Its links point at news.google.com, so the publisher is the real source.
    Returns ``{"domain", "label", "reason"}``.
    """
    domain = _domain(url)
    text = f"{title} {content}".lower()

    publisher = (publisher or "").strip().lower()
    if publisher:
        mapped = PUBLISHER_TO_DOMAIN.get(publisher)
        if mapped:
            domain = mapped
        else:
            # Real attribution we do not recognise: name it, do not trust it.
            domain = publisher.replace(" ", "")
            return {"domain": domain, "label": LABEL_DEVELOPING,
                    "reason": f"publisher '{publisher}' is not on the trusted list"}
    if domain == "news.google.com":
        # Aggregator landing page with no attribution: not a real source.
        return {"domain": domain, "label": LABEL_DEVELOPING,
                "reason": "news aggregator page, no publisher attributed"}

    if _is_press_release(domain):
        return {"domain": domain, "label": LABEL_PROMOTIONAL,
                "reason": f"wire-service press release ({domain})"}

    marker = next((m for m in PROMOTIONAL_MARKERS if m in text), None)
    if marker:
        return {"domain": domain, "label": LABEL_PROMOTIONAL,
                "reason": f"marked '{marker}'"}

    if _is_trusted(domain):
        return {"domain": domain, "label": LABEL_VERIFIED,
                "reason": f"recognised news organisation ({domain})"}

    if not domain:
        return {"domain": domain, "label": LABEL_DEVELOPING,
                "reason": "no source URL provided"}

    return {"domain": domain, "label": LABEL_DEVELOPING,
            "reason": f"single lesser-known source ({domain})"}


def assess(results: List[Dict]) -> List[Dict]:
    """Classify a list of search results, preserving the original fields."""
    labelled = []
    for result in results or []:
        if not isinstance(result, dict):
            continue
        entry = dict(result)
        entry.update(classify(
            result.get("title", ""), result.get("url", ""),
            result.get("content", ""), result.get("publisher", ""),
        ))
        labelled.append(entry)
    return labelled


def overall(labelled: List[Dict]) -> str:
    """Overall confidence for a set of labelled results."""
    if not labelled:
        return "unknown"
    labels = {r.get("label") for r in labelled}
    if LABEL_VERIFIED in labels:
        return LABEL_VERIFIED
    if labels == {LABEL_PROMOTIONAL}:
        return LABEL_PROMOTIONAL
    return LABEL_DEVELOPING


def format_for_model(labelled: List[Dict]) -> str:
    """Render labelled results as text the model can cite directly."""
    lines = []
    for r in labelled:
        publisher = r.get("publisher")
        source = publisher or r.get("domain") or "unknown"
        lines.append(
            f"- [{r.get('label')}] {r.get('title', '').strip()}\n"
            f"    source: {source} ({r.get('reason')})\n"
            f"    url: {r.get('url') or 'none'}"
        )
    return "\n".join(lines)
