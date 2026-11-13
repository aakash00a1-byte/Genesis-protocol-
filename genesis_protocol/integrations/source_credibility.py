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

``TRUSTED_SOURCES`` is the single source of truth: a domain maps to the
publisher names it uses in Google News titles. ``TRUSTED_NEWS_DOMAINS`` and
``PUBLISHER_TO_DOMAIN`` are derived from it, so the two can never drift apart.
"""

from typing import Any, Dict, List
from urllib.parse import urlparse

# Domain -> the publisher names it appears under in Google News titles.
# Grouped by region only for readability; the mapping is what matters.
TRUSTED_SOURCES: Dict[str, tuple] = {
    # --- International wires and broadcasters ---
    "reuters.com": ("reuters",),
    "apnews.com": ("the associated press", "ap", "associated press"),
    "afp.com": ("afp", "agence france-presse"),
    "bbc.com": ("bbc news", "bbc", "bbc world"),
    "aljazeera.com": ("al jazeera", "al jazeera english"),
    "dw.com": ("deutsche welle", "dw"),
    "france24.com": ("france 24",),
    "euronews.com": ("euronews",),
    "cnn.com": ("cnn",),
    "npr.org": ("npr",),
    "theguardian.com": ("the guardian", "guardian"),

    # --- United States ---
    "nytimes.com": ("the new york times",),
    "washingtonpost.com": ("the washington post", "washington post"),
    "wsj.com": ("the wall street journal", "wsj"),
    "usatoday.com": ("usa today",),
    "latimes.com": ("los angeles times",),
    "nbcnews.com": ("nbc news",),
    "abcnews.go.com": ("abc news",),
    "cbsnews.com": ("cbs news",),
    "politico.com": ("politico",),
    "axios.com": ("axios",),
    "theatlantic.com": ("the atlantic",),
    "time.com": ("time",),
    "newsweek.com": ("newsweek",),
    "vox.com": ("vox",),
    "slate.com": ("slate",),
    "businessinsider.com": ("business insider",),
    "investors.com": ("investor's business daily", "investors business daily"),
    "analyticsindiamag.com": ("analytics india magazine",),
    "iapp.org": ("iapp", "international association of privacy professionals"),
    "news.un.org": ("un news",),
    "unesco.org": ("unesco",),
    "cnbc.com": ("cnbc",),
    "forbes.com": ("forbes",),
    "fortune.com": ("fortune",),
    "barrons.com": ("barron's",),
    "marketwatch.com": ("marketwatch",),
    "bloomberg.com": ("bloomberg",),
    "theinformation.com": ("the information",),

    # --- United Kingdom ---
    "telegraph.co.uk": ("the telegraph", "telegraph"),
    "thetimes.co.uk": ("the times",),
    "independent.co.uk": ("the independent",),
    "ft.com": ("financial times",),
    "economist.com": ("the economist",),
    "news.sky.com": ("sky news",),
    "thesun.co.uk": ("the sun",),
    "dailymail.co.uk": ("daily mail",),

    # --- India ---
    "thehindu.com": ("the hindu",),
    "indianexpress.com": ("the indian express", "indian express"),
    "timesofindia.indiatimes.com": ("the times of india", "times of india"),
    "hindustantimes.com": ("hindustan times",),
    "livemint.com": ("livemint", "mint"),
    "business-standard.com": ("business standard",),
    "economictimes.indiatimes.com": ("the economic times", "economic times"),
    "ndtv.com": ("ndtv",),
    "thewire.in": ("the wire",),
    "scroll.in": ("scroll.in",),
    "indiatoday.in": ("india today",),
    "firstpost.com": ("firstpost",),
    "theprint.in": ("the print",),
    "deccanherald.com": ("deccan herald",),
    "telegraphindia.com": ("the telegraph india",),
    "moneycontrol.com": ("moneycontrol",),
    "financialexpress.com": ("the financial express",),
    "zeenews.india.com": ("zee news",),
    "news18.com": ("news18",),
    "abplive.com": ("abp live",),
    "tribuneindia.com": ("the tribune",),

    # --- Technology ---
    "techcrunch.com": ("techcrunch",),
    "arstechnica.com": ("ars technica",),
    "wired.com": ("wired",),
    "theverge.com": ("the verge",),
    "zdnet.com": ("zdnet",),
    "venturebeat.com": ("venturebeat",),
    "theregister.com": ("the register",),
    "engadget.com": ("engadget",),
    "gizmodo.com": ("gizmodo",),
    "cnet.com": ("cnet",),
    "macrumors.com": ("macrumors",),
    "9to5mac.com": ("9to5mac",),
    "androidpolice.com": ("android police",),
    "techradar.com": ("techradar",),
    "thenextweb.com": ("the next web",),
    "spectrum.ieee.org": ("ieee spectrum",),
    "restofworld.org": ("rest of world",),
    "news.mit.edu": ("mit news",),
    "technologyreview.com": ("mit technology review",),

    # --- Science and health ---
    "nature.com": ("nature",),
    "science.org": ("science",),
    "sciencedaily.com": ("sciencedaily",),
    "newscientist.com": ("new scientist",),
    "scientificamerican.com": ("scientific american",),
    "space.com": ("space.com",),
    "nasa.gov": ("nasa",),
    "phys.org": ("phys.org",),
    "thelancet.com": ("the lancet",),
    "nejm.org": ("the new england journal of medicine",),
    "statnews.com": ("stat",),
    "quantamagazine.org": ("quanta magazine",),
    "medicalxpress.com": ("medical xpress",),

    # --- Business and analysis ---
    "hbr.org": ("harvard business review",),

    # --- Asia-Pacific ---
    "scmp.com": ("south china morning post",),
    "straitstimes.com": ("the straits times",),
    "channelnewsasia.com": ("cna", "channel newsasia"),
    "abc.net.au": ("abc news", "abc news australia"),
    "smh.com.au": ("the sydney morning herald",),
    "theage.com.au": ("the age",),
    "japantimes.co.jp": ("the japan times",),
    "koreaherald.com": ("the korea herald",),
    "asia.nikkei.com": ("nikkei asia",),
    "caixinglobal.com": ("caixin",),

    # --- Europe, Middle East, Africa ---
    "lemonde.fr": ("le monde",),
    "spiegel.de": ("der spiegel",),
    "haaretz.com": ("haaretz",),
    "jpost.com": ("the jerusalem post",),
    "timesofisrael.com": ("the times of israel",),
    "middleeasteye.net": ("middle east eye",),
    "alarabiya.net": ("al arabiya",),
    "africanews.com": ("africanews",),

    # --- Canada ---
    "cbc.ca": ("cbc news",),
    "theglobeandmail.com": ("the globe and mail",),
    "globalnews.ca": ("global news",),
}

# Wire services whose content is normally paid/self-submitted, i.e. promotional
# unless a newsroom has picked it up separately.
PRESS_RELEASE_DOMAINS = {
    "globenewswire.com", "prnewswire.com", "businesswire.com", "accesswire.com",
    "einpresswire.com", "prlog.org", "openpr.com", "newsfilecorp.com",
    "pressreleasepoint.com", "issuewire.com", "send2press.com",
    "prweb.com", "newswire.com", "digitaljournal.com", "streetinsider.com",
}

# Words that mark content as paid or self-promotional.
PROMOTIONAL_MARKERS = (
    "sponsored", "press release", "prnewswire", "paid post", "advertorial",
    "promoted content", "partner content", "brand post", "self-reported",
    "sponsored content", "in partnership with", "brought to you by",
    "advertisement feature",
)

LABEL_VERIFIED = "verified"
LABEL_DEVELOPING = "developing"
LABEL_PROMOTIONAL = "promotional-unverified"

# Derived views, kept in sync automatically.
TRUSTED_NEWS_DOMAINS = set(TRUSTED_SOURCES)


_TLD_SUFFIXES = (".com", ".in", ".co.uk", ".co", ".org", ".net", ".news",
                 ".uk", ".au", ".io")


def _normalize_publisher(name: str) -> str:
    """Lowercase a publisher name and strip a trailing site suffix.

    Google News titles vary: "Bloomberg" and "Bloomberg.com", "Business Insider"
    and "Business Insider India". Normalising lets those resolve to one source.
    """
    name = (name or "").strip().lower()
    for suffix in _TLD_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return " ".join(name.split())


def _build_publisher_index():
    """Map publisher aliases to domains, flagging names that are ambiguous.

    "ABC News" is both the US and the Australian broadcaster, so a bare name
    cannot be resolved. Those aliases are dropped from the map and reported as
    ambiguous instead of being confidently labelled as either.
    """
    index: Dict[str, str] = {}
    ambiguous = set()
    for domain, aliases in TRUSTED_SOURCES.items():
        for alias in aliases:
            alias = _normalize_publisher(alias)
            if alias in index and index[alias] != domain:
                ambiguous.add(alias)
            else:
                index[alias] = domain
    for alias in ambiguous:
        index.pop(alias, None)
    return index, ambiguous


def _resolve_publisher(publisher: str):
    """Resolve a publisher name to a domain, or ``(None, reason)``.

    Tries an exact match, then the longest trusted alias that is a whole-word
    prefix, so "business insider india" resolves to businessinsider.com while a
    bare ambiguous name is refused.
    """
    name = _normalize_publisher(publisher)
    if name in AMBIGUOUS_PUBLISHERS:
        return None, f"publisher name '{name}' is ambiguous (more than one outlet uses it)"
    if name in PUBLISHER_TO_DOMAIN:
        return PUBLISHER_TO_DOMAIN[name], None
    best_alias = ""
    for alias in PUBLISHER_TO_DOMAIN:
        if alias and (name == alias or name.startswith(alias + " ")):
            if len(alias) > len(best_alias):
                best_alias = alias
    if best_alias:
        return PUBLISHER_TO_DOMAIN[best_alias], None
    return None, f"publisher '{name}' is not on the trusted list"


PUBLISHER_TO_DOMAIN, AMBIGUOUS_PUBLISHERS = _build_publisher_index()


def _domain(url: str) -> str:
    netloc = urlparse(url or "").netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _matches(domain: str, candidates) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in candidates)


def _is_trusted(domain: str) -> bool:
    return _matches(domain, TRUSTED_NEWS_DOMAINS)


def _is_press_release(domain: str) -> bool:
    return _matches(domain, PRESS_RELEASE_DOMAINS)


def classify(title: str, url: str, content: str = "",
             publisher: str = "") -> Dict[str, Any]:
    """Label one search result.

    ``publisher`` is the attribution Google News adds ("Headline - Publisher").
    Its links point at news.google.com, so the publisher is the real source.
    Returns ``{"domain", "label", "reason"}``.
    """
    domain = _domain(url)
    text = f"{title} {content}".lower()

    publisher = (publisher or "").strip()
    if publisher:
        mapped, problem = _resolve_publisher(publisher)
        if mapped:
            domain = mapped
        else:
            # Real attribution we cannot resolve: name it, do not trust it.
            return {"domain": _normalize_publisher(publisher).replace(" ", ""),
                    "label": LABEL_DEVELOPING, "reason": problem}

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


def group_by_label(labelled: List[Dict]) -> Dict[str, List[Dict]]:
    """Split labelled results into sections, strongest evidence first."""
    return {
        LABEL_VERIFIED: [r for r in labelled if r.get("label") == LABEL_VERIFIED],
        LABEL_DEVELOPING: [r for r in labelled if r.get("label") == LABEL_DEVELOPING],
        LABEL_PROMOTIONAL: [r for r in labelled if r.get("label") == LABEL_PROMOTIONAL],
    }


_SECTION_TITLES = {
    LABEL_VERIFIED: "VERIFIED (recognised news organisations)",
    LABEL_DEVELOPING: "DEVELOPING (single or unknown source)",
    LABEL_PROMOTIONAL: "PROMOTIONAL / UNVERIFIED (not independent reporting)",
}


def _render_item(r: Dict) -> str:
    publisher = r.get("publisher")
    source = publisher or r.get("domain") or "unknown"
    return (
        f"- {r.get('title', '').strip()}\n"
        f"    source: {source} ({r.get('reason')})\n"
        f"    url: {r.get('url') or 'none'}"
    )


def format_for_model(labelled: List[Dict]) -> str:
    """Render labelled results as sectioned text the model can cite directly.

    Grouping keeps promotional and single-source items visibly apart from
    verified reporting, so the model cannot quietly present them as equal.
    """
    sections = group_by_label(labelled)
    blocks = []
    for label in (LABEL_VERIFIED, LABEL_DEVELOPING, LABEL_PROMOTIONAL):
        items = sections[label]
        if not items:
            continue
        blocks.append(f"=== {_SECTION_TITLES[label]} ===")
        blocks.extend(_render_item(r) for r in items)
    return "\n".join(blocks)
