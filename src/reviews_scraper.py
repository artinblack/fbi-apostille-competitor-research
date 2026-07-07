"""
Reviews & trust signals scraper.
1. Google Places / Maps — uses Serper's /places endpoint to find ratings and review counts.
2. Trustpilot — scrapes trustpilot.com/{domain} via Firecrawl/Jina.
"""

import re
import time
from dataclasses import dataclass

import requests

import config


SERPER_PLACES_ENDPOINT = "https://google.serper.dev/places"


@dataclass
class ReviewData:
    url: str
    google_rating: float = 0.0
    google_review_count: int = 0
    google_place_name: str = ""
    trustpilot_rating: float = 0.0
    trustpilot_review_count: int = 0
    trustpilot_url: str = ""
    justdial_rating: float = 0.0
    overall_trust_score: str = ""   # "High" / "Medium" / "Low" / "None"
    error: str = ""


def _search_google_places(domain: str) -> tuple[float, int, str]:
    """Search Google Maps for the business. Returns (rating, review_count, place_name)."""
    if not config.SERPER_API_KEY:
        return 0.0, 0, ""

    clean = domain.replace("www.", "").split(".")[0]
    payload = {"q": f"{clean} apostille", "gl": "us", "hl": "en"}
    headers = {"X-API-KEY": config.SERPER_API_KEY, "Content-Type": "application/json"}

    try:
        resp = requests.post(SERPER_PLACES_ENDPOINT, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        places = resp.json().get("places", [])
        if places:
            top = places[0]
            return (
                float(top.get("rating", 0)),
                int(top.get("ratingCount", 0)),
                top.get("title", ""),
            )
    except Exception:
        pass
    return 0.0, 0, ""


def _scrape_trustpilot(domain: str) -> tuple[float, int, str]:
    """Scrape Trustpilot review page. Returns (rating, count, trustpilot_url)."""
    clean = domain.replace("www.", "")
    tp_url = f"https://www.trustpilot.com/review/{clean}"

    text = ""
    if config.FIRECRAWL_API_KEY:
        try:
            from firecrawl import FirecrawlApp
            app = FirecrawlApp(api_key=config.FIRECRAWL_API_KEY)
            result = app.scrape_url(tp_url, params={"formats": ["markdown"]})
            text = result.get("markdown", "")
        except Exception:
            pass

    if not text:
        try:
            resp = requests.get(
                f"https://r.jina.ai/{tp_url}",
                headers={"User-Agent": "ApostilleResearchBot/1.0"},
                timeout=20,
            )
            text = resp.text
        except Exception:
            return 0.0, 0, ""

    lower = text.lower()
    rating = 0.0
    count = 0

    # Extract rating (e.g. "4.8 out of 5" or "TrustScore 4.8")
    for pat in [r"trustscore\s+([\d.]+)", r"([\d.]+)\s+out of\s+5", r"rated\s+([\d.]+)"]:
        match = re.search(pat, lower)
        if match:
            try:
                rating = float(match.group(1))
                break
            except ValueError:
                pass

    # Extract review count (e.g. "1,234 reviews")
    for pat in [r"([\d,]+)\s+reviews?", r"based on\s+([\d,]+)"]:
        match = re.search(pat, lower)
        if match:
            try:
                count = int(match.group(1).replace(",", ""))
                break
            except ValueError:
                pass

    if rating > 0 or count > 0:
        return rating, count, tp_url
    return 0.0, 0, ""


def _trust_score_label(google_rating: float, google_count: int,
                        tp_rating: float, tp_count: int) -> str:
    total_reviews = google_count + tp_count
    avg_rating = (google_rating + tp_rating) / max(
        1, (1 if google_rating else 0) + (1 if tp_rating else 0)
    )
    if total_reviews >= 100 and avg_rating >= 4.0:
        return "High"
    if total_reviews >= 20 or avg_rating >= 3.5:
        return "Medium"
    if total_reviews > 0:
        return "Low"
    return "None"


def scrape(url: str) -> ReviewData:
    """Fetch Google Places rating + Trustpilot rating for a competitor URL."""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc

    data = ReviewData(url=url)

    # Google Places
    data.google_rating, data.google_review_count, data.google_place_name = \
        _search_google_places(domain)

    time.sleep(1)

    # Trustpilot
    data.trustpilot_rating, data.trustpilot_review_count, data.trustpilot_url = \
        _scrape_trustpilot(domain)

    data.overall_trust_score = _trust_score_label(
        data.google_rating, data.google_review_count,
        data.trustpilot_rating, data.trustpilot_review_count,
    )

    return data


def scrape_all(competitors: list) -> dict[str, ReviewData]:
    """Scrape review data for all competitors."""
    results: dict[str, ReviewData] = {}
    total = len(competitors)
    for i, comp in enumerate(competitors, 1):
        print(f"  [{i}/{total}] Reviews: {comp.domain}")
        results[comp.url] = scrape(comp.url)
        r = results[comp.url]
        g = f"Google={r.google_rating}★({r.google_review_count})" if r.google_rating else "Google=none"
        t = f"Trustpilot={r.trustpilot_rating}★({r.trustpilot_review_count})" if r.trustpilot_rating else "Trustpilot=none"
        print(f"    ✓ {g} | {t} | Trust={r.overall_trust_score}")
        time.sleep(1)
    return results
