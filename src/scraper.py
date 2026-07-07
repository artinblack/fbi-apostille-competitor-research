"""
Website scraper — uses Firecrawl as primary (LLM-optimised markdown + metadata),
falls back to Jina AI Reader (free, no key, static sites) on any failure.
Includes per-domain caching (7-day TTL) and exponential-backoff retry logic.
"""

import time
import re
from dataclasses import dataclass, asdict

import requests

import config
from src import cache as _cache


JINA_BASE = "https://r.jina.ai/"
_MAX_RETRIES = 3

# Signal keywords scanned from page markdown
_SIGNALS = {
    "has_testimonials": ["testimonial", "review", "★", "5 star", "4 star", "rated",
                         "trustpilot", "google review", "what our clients say", "customer speak",
                         "satisfied client", "happy customer"],
    "has_newsletter":   ["subscribe", "newsletter", "email updates", "get updates", "mailing list",
                         "join our list"],
    "has_blog":         ["blog", "article", "resources", "knowledge base", "insights",
                         "latest post", "news", "guide"],
    "has_pricing":      ["₹", "$", "usd", "inr", "price", "fee", "cost", "charge",
                         "starting from", "package", "rate", "per document", "flat rate"],
    "has_whatsapp":     ["whatsapp", "wa.me", "chat on whatsapp", "whatsapp us"],
    "has_form":         ["contact us", "get a quote", "free quote", "submit", "inquiry",
                         "enquiry", "request", "book now", "apply now", "get started"],
    "has_live_chat":    ["live chat", "chat now", "tawk.to", "intercom", "crisp",
                         "freshchat", "tidio", "drift"],
    # New signals
    "has_multilingual": ["हिन्दी", "हिंदी", "hindi", "اردو", "বাংলা", "తెలుగు", "தமிழ்",
                         "kannada", "marathi", "language", "भाषा"],
    "has_chatbot":      ["chatbot", "ai chat", "automated response", "bot", "virtual assistant",
                         "chat with ai", "ai assistant"],
    "has_youtube":      ["youtube.com", "youtu.be", "watch?v=", "youtube channel",
                         "video tutorial"],
    "has_tracking":     ["track your", "track order", "tracking portal", "document status",
                         "check status", "track document"],
    "has_express":      ["express", "urgent", "same day", "24 hour", "rush", "expedited",
                         "fast track", "priority"],
    "has_guarantee":    ["guarantee", "money back", "refund", "100%", "assured",
                         "satisfaction guaranteed", "rejection free"],
}

# Social media platforms to detect links for
_SOCIAL_PLATFORMS = {
    "facebook":  ["facebook.com/", "fb.com/"],
    "instagram": ["instagram.com/"],
    "linkedin":  ["linkedin.com/company/", "linkedin.com/in/"],
    "twitter":   ["twitter.com/", "x.com/"],
    "youtube":   ["youtube.com/channel/", "youtube.com/@", "youtube.com/c/", "youtu.be/"],
    "pinterest": ["pinterest.com/"],
}


@dataclass
class ScrapedData:
    url: str
    title: str = ""
    meta_description: str = ""
    markdown: str = ""
    scrape_method: str = ""       # "firecrawl" | "jina" | "cache" | "failed"
    # Core signals
    has_testimonials: bool = False
    has_newsletter: bool = False
    has_blog: bool = False
    has_pricing: bool = False
    has_whatsapp: bool = False
    has_form: bool = False
    has_live_chat: bool = False
    # New signals
    has_multilingual: bool = False
    has_chatbot: bool = False
    has_youtube: bool = False
    has_tracking: bool = False
    has_express: bool = False
    has_guarantee: bool = False
    # Social media links detected
    social_links: dict = None
    error: str = ""

    def __post_init__(self):
        if self.social_links is None:
            self.social_links = {}

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ScrapedData":
        d.pop("_cached_at", None)
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def _detect_signals(text: str) -> dict[str, bool]:
    lower = text.lower()
    return {key: any(kw in lower for kw in kws) for key, kws in _SIGNALS.items()}


def _detect_social_links(text: str) -> dict[str, str]:
    """Extract social media profile URLs from page markdown."""
    lower = text.lower()
    found = {}
    for platform, patterns in _SOCIAL_PLATFORMS.items():
        for pat in patterns:
            idx = lower.find(pat)
            if idx != -1:
                # Extract ~60 chars from that position to get the full URL
                snippet = text[max(0, idx - 10):idx + 80]
                # Pull URL from snippet
                import re
                match = re.search(r'https?://[^\s\)\]"\'<>]+', snippet)
                if match:
                    found[platform] = match.group(0).rstrip("/.,)")
                    break
    return found


def _retry(fn, max_retries: int = _MAX_RETRIES):
    """Call fn() with exponential backoff. Re-raises final exception."""
    last_exc = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                time.sleep(wait)
    raise last_exc


def _scrape_firecrawl(url: str) -> ScrapedData:
    if not config.FIRECRAWL_API_KEY:
        raise ValueError("FIRECRAWL_API_KEY is not set in .env")

    from firecrawl import FirecrawlApp
    app = FirecrawlApp(api_key=config.FIRECRAWL_API_KEY)

    def _call():
        return app.scrape_url(url, params={"formats": ["markdown"]})

    result = _retry(_call)

    markdown = result.get("markdown") or ""
    metadata = result.get("metadata") or {}

    title = metadata.get("title") or metadata.get("ogTitle") or ""
    description = metadata.get("description") or metadata.get("ogDescription") or ""

    signals = _detect_signals(markdown)
    social = _detect_social_links(markdown)

    return ScrapedData(
        url=url,
        title=title,
        meta_description=description,
        markdown=markdown,
        scrape_method="firecrawl",
        social_links=social,
        **signals,
    )


def _scrape_jina(url: str) -> ScrapedData:
    """Free fallback using Jina AI Reader — no API key required."""
    def _call():
        jina_url = JINA_BASE + url
        headers = {"User-Agent": "ApostilleResearchBot/1.0", "Accept": "text/plain"}
        resp = requests.get(jina_url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.text

    markdown = _retry(_call)

    title = ""
    description = ""
    for line in markdown.splitlines()[:10]:
        if line.startswith("Title:"):
            title = line.removeprefix("Title:").strip()
        elif line.startswith("Description:"):
            description = line.removeprefix("Description:").strip()

    signals = _detect_signals(markdown)
    social = _detect_social_links(markdown)

    return ScrapedData(
        url=url,
        title=title,
        meta_description=description,
        markdown=markdown,
        scrape_method="jina",
        social_links=social,
        **signals,
    )


def scrape(url: str, use_cache: bool = True) -> ScrapedData:
    """
    Scrape a competitor URL. Checks cache first (7-day TTL), then tries
    Firecrawl with retry, falls back to Jina AI Reader.
    """
    if use_cache:
        cached = _cache.get(url)
        if cached:
            try:
                data = ScrapedData.from_dict(cached)
                data.scrape_method = "cache"
                return data
            except Exception:
                pass

    # ── Firecrawl attempt ──────────────────────────────────────────────────────
    if config.FIRECRAWL_API_KEY:
        try:
            data = _scrape_firecrawl(url)
            _cache.set(url, data.to_dict())
            print(f"    ✓ Firecrawl OK ({len(data.markdown)} chars)")
            return data
        except Exception as e:
            print(f"    ✗ Firecrawl failed ({e}), trying Jina fallback…")

    # ── Jina fallback ──────────────────────────────────────────────────────────
    try:
        data = _scrape_jina(url)
        _cache.set(url, data.to_dict())
        print(f"    ✓ Jina fallback OK ({len(data.markdown)} chars)")
        return data
    except Exception as e:
        print(f"    ✗ Jina also failed ({e})")
        return ScrapedData(url=url, scrape_method="failed", error=str(e))


def scrape_all(
    competitors: list,
    delay: float = config.REQUEST_DELAY,
    use_cache: bool = True,
) -> dict[str, ScrapedData]:
    """Scrape all competitors. Returns {url: ScrapedData}."""
    results: dict[str, ScrapedData] = {}
    total = len(competitors)
    for i, comp in enumerate(competitors, 1):
        print(f"  [{i}/{total}] {comp.url}")
        result = scrape(comp.url, use_cache=use_cache)
        if result.scrape_method == "cache":
            print(f"    → loaded from cache")
        results[comp.url] = result
        if i < total and result.scrape_method != "cache":
            time.sleep(delay)
    return results
