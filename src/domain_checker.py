"""
Domain authority & backlink snapshot using Open PageRank API (free tier).
Also detects YouTube channel presence by searching YouTube via Serper.

Open PageRank: https://www.domcop.com/openpagerank/
Free API key at: https://openpagerank.com/
"""

import re
import time
from dataclasses import dataclass

import requests

import config


OPR_ENDPOINT = "https://openpagerank.com/api/v1.0/getPageRank"
SERPER_ENDPOINT = "https://google.serper.dev/search"


@dataclass
class DomainData:
    url: str
    domain: str = ""
    page_rank: float = 0.0        # Open PageRank (0–10 scale)
    domain_authority: int = 0     # Estimated DA (derived from PR)
    rank_global: int = 0          # Alexa-style global rank (if available)
    backlink_count: str = ""      # Estimated backlinks (string, e.g. "2.1K")
    youtube_channel: str = ""     # YouTube channel URL if found
    youtube_videos: int = 0       # Estimated video count
    domain_age_note: str = ""     # e.g. "Established (high DA)" vs "New domain"
    error: str = ""


def _get_page_rank(domain: str) -> tuple[float, int]:
    """
    Query Open PageRank API. Returns (page_rank, estimated_da).
    Requires OPEN_PAGERANK_API_KEY in .env.
    """
    key = config.OPEN_PAGERANK_API_KEY if hasattr(config, "OPEN_PAGERANK_API_KEY") else ""
    if not key:
        return 0.0, 0

    try:
        resp = requests.get(
            OPR_ENDPOINT,
            params={"domains[]": domain},
            headers={"API-OPR": key},
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json().get("response", [{}])[0]
        pr = float(result.get("page_rank_decimal", 0) or 0)
        # Map 0–10 PR to rough 0–100 DA scale
        da = int(pr * 10)
        return pr, da
    except Exception:
        return 0.0, 0


def _find_youtube_channel(domain: str) -> tuple[str, int]:
    """Search for the competitor's YouTube channel via Serper."""
    if not config.SERPER_API_KEY:
        return "", 0

    clean = domain.replace("www.", "").split(".")[0]
    payload = {
        "q": f"{clean} apostille youtube channel",
        "gl": "in", "hl": "en", "num": 5,
    }
    headers = {"X-API-KEY": config.SERPER_API_KEY, "Content-Type": "application/json"}

    try:
        resp = requests.post(SERPER_ENDPOINT, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        for result in resp.json().get("organic", []):
            link = result.get("link", "")
            if "youtube.com" in link and ("channel" in link or "@" in link or "/c/" in link):
                return link, 0  # video count not easily extractable from SERP
    except Exception:
        pass
    return "", 0


def _estimate_backlinks(pr: float) -> str:
    """Rough backlink estimate from PageRank score."""
    if pr >= 7:
        return "100K+"
    if pr >= 5:
        return "10K–100K"
    if pr >= 3:
        return "1K–10K"
    if pr >= 1:
        return "100–1K"
    return "<100 (new/low authority)"


def _domain_age_note(pr: float) -> str:
    if pr >= 5:
        return "Established (high authority)"
    if pr >= 2:
        return "Growing (moderate authority)"
    return "New or low-authority domain"


def check(url: str) -> DomainData:
    from urllib.parse import urlparse
    domain = urlparse(url).netloc

    data = DomainData(url=url, domain=domain)

    pr, da = _get_page_rank(domain)
    data.page_rank = pr
    data.domain_authority = da
    data.backlink_count = _estimate_backlinks(pr)
    data.domain_age_note = _domain_age_note(pr)

    time.sleep(0.5)

    data.youtube_channel, data.youtube_videos = _find_youtube_channel(domain)

    return data


def check_all(competitors: list) -> dict[str, DomainData]:
    """Check domain authority + YouTube for all competitors."""
    results: dict[str, DomainData] = {}
    total = len(competitors)
    for i, comp in enumerate(competitors, 1):
        print(f"  [{i}/{total}] Domain: {comp.domain}")
        results[comp.url] = check(comp.url)
        d = results[comp.url]
        yt = f"YouTube: {d.youtube_channel[:40]}" if d.youtube_channel else "No YouTube"
        pr_str = f"PR={d.page_rank}" if d.page_rank else "PR=unknown (no OPR key)"
        print(f"    ✓ {pr_str} | DA≈{d.domain_authority} | {yt}")
        time.sleep(1)
    return results
