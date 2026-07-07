"""
Social media & Google Ads intelligence.

1. Social media: extracts profile links from scraped markdown, then uses
   Firecrawl to fetch public follower/post counts from each profile page.

2. Google Ads Transparency: scrapes adstransparency.google.com to check
   if a competitor is running active Google Ads, extracts ad copy snippets.
"""

import re
import time
from dataclasses import dataclass, field

import requests

import config


@dataclass
class SocialData:
    url: str
    facebook_url: str = ""
    instagram_url: str = ""
    linkedin_url: str = ""
    twitter_url: str = ""
    youtube_url: str = ""
    facebook_followers: str = ""
    instagram_followers: str = ""
    linkedin_followers: str = ""
    youtube_subscribers: str = ""
    active_platforms: list = field(default_factory=list)
    is_running_ads: bool = False
    ads_copy_samples: list = field(default_factory=list)
    error: str = ""


_FOLLOWER_PATTERNS = [
    r"([\d,\.]+[KMB]?)\s*(?:followers|subscribers|fans|likes)",
    r"(?:followers|subscribers|fans|likes)[:\s]*([\d,\.]+[KMB]?)",
]


def _extract_follower_count(text: str) -> str:
    lower = text.lower()
    for pat in _FOLLOWER_PATTERNS:
        match = re.search(pat, lower)
        if match:
            return match.group(1)
    return ""


def _scrape_url_text(url: str) -> str:
    """Fetch page as markdown via Firecrawl or Jina."""
    if config.FIRECRAWL_API_KEY:
        try:
            from firecrawl import FirecrawlApp
            app = FirecrawlApp(api_key=config.FIRECRAWL_API_KEY)
            result = app.scrape_url(url, params={"formats": ["markdown"]})
            return result.get("markdown") or ""
        except Exception:
            pass
    try:
        resp = requests.get(f"https://r.jina.ai/{url}",
                            headers={"User-Agent": "ApostilleResearchBot/1.0"},
                            timeout=20)
        return resp.text
    except Exception:
        return ""


def _check_google_ads(domain: str) -> tuple[bool, list[str]]:
    """
    Check Google Ads Transparency Center for the domain.
    Returns (is_running_ads, [ad_copy_samples]).
    """
    clean = domain.replace("www.", "")
    ads_url = f"https://adstransparency.google.com/advertiser?query={clean}&region=IN"
    text = _scrape_url_text(ads_url)
    lower = text.lower()

    # If the page mentions the domain in an advertiser context, they're running ads
    is_running = (
        clean in lower
        and any(kw in lower for kw in ["advertiser", "ad", "sponsored", "campaign"])
    )

    # Extract any ad copy snippets (lines that look like ad headlines)
    samples = []
    for line in text.splitlines():
        line = line.strip()
        if 10 < len(line) < 90 and not line.startswith("#") and not line.startswith("http"):
            if any(kw in line.lower() for kw in ["apostille", "document", "certificate",
                                                   "attestation", "authentication"]):
                samples.append(line)
        if len(samples) >= 3:
            break

    return is_running, samples


def analyze(url: str, scraped_data) -> SocialData:
    """
    Build SocialData for a competitor using their already-scraped content
    plus optional deeper social profile + ads checks.
    """
    from src.scraper import ScrapedData
    data = SocialData(url=url)

    # ── Extract social links from scraped markdown ─────────────────────────────
    links = getattr(scraped_data, "social_links", {}) or {}
    data.facebook_url  = links.get("facebook", "")
    data.instagram_url = links.get("instagram", "")
    data.linkedin_url  = links.get("linkedin", "")
    data.twitter_url   = links.get("twitter", "")
    data.youtube_url   = links.get("youtube", "")

    active = [p for p, v in {
        "Facebook":  data.facebook_url,
        "Instagram": data.instagram_url,
        "LinkedIn":  data.linkedin_url,
        "Twitter/X": data.twitter_url,
        "YouTube":   data.youtube_url,
    }.items() if v]
    data.active_platforms = active

    # ── Fetch follower counts from public pages ────────────────────────────────
    for platform, profile_url, attr in [
        ("facebook",  data.facebook_url,  "facebook_followers"),
        ("instagram", data.instagram_url, "instagram_followers"),
        ("linkedin",  data.linkedin_url,  "linkedin_followers"),
        ("youtube",   data.youtube_url,   "youtube_subscribers"),
    ]:
        if profile_url:
            try:
                text = _scrape_url_text(profile_url)
                count = _extract_follower_count(text)
                setattr(data, attr, count)
                time.sleep(1)
            except Exception:
                pass

    # ── Google Ads Transparency check ─────────────────────────────────────────
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.removeprefix("www.")
    try:
        data.is_running_ads, data.ads_copy_samples = _check_google_ads(domain)
    except Exception as e:
        data.error = str(e)

    return data


def analyze_all(competitors: list, scraped_map: dict) -> dict[str, SocialData]:
    """Run social + ads analysis for all competitors."""
    results: dict[str, SocialData] = {}
    total = len(competitors)
    for i, comp in enumerate(competitors, 1):
        print(f"  [{i}/{total}] Social/Ads: {comp.domain}")
        scraped = scraped_map.get(comp.url)
        results[comp.url] = analyze(comp.url, scraped)
        s = results[comp.url]
        platforms = ", ".join(s.active_platforms) if s.active_platforms else "None detected"
        ads_str = "Running ads" if s.is_running_ads else "No ads detected"
        print(f"    ✓ Platforms: {platforms} | {ads_str}")
    return results
