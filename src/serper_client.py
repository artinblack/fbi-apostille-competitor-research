"""
Serper API client — searches keywords via Google US results and aggregates
unique competitor domains with their SERP positions.
"""

import time
from urllib.parse import urlparse
from dataclasses import dataclass, field

import requests

import config


SERPER_ENDPOINT = "https://google.serper.dev/search"


@dataclass
class SERPResult:
    position: int
    title: str
    link: str
    snippet: str
    keyword: str


@dataclass
class CompetitorSERP:
    domain: str
    url: str
    keywords: list[str] = field(default_factory=list)
    positions: list[int] = field(default_factory=list)

    @property
    def best_position(self) -> int:
        return min(self.positions) if self.positions else 999

    @property
    def avg_position(self) -> float:
        return round(sum(self.positions) / len(self.positions), 1) if self.positions else 999.0

    @property
    def keyword_count(self) -> int:
        return len(self.keywords)


def _extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        return domain.removeprefix("www.")
    except Exception:
        return url


def _is_noise(url: str) -> bool:
    """Filter out non-competitor URLs (aggregators, government sites, Q&A sites, etc.)."""
    noise_domains = {
        "reddit.com", "quora.com", "wikipedia.org", "youtube.com",
        "facebook.com", "linkedin.com", "instagram.com", "twitter.com",
        "x.com", "amazon.com", "yelp.com", "trustpilot.com",
    }
    domain = _extract_domain(url)

    # Government, military, and educational institutions are not competitors:
    #   .gov / .mil / .edu  → federal & state agencies, embassies, universities
    #   sos.* / *.state.*.us → Secretary-of-State apostille offices (e.g. sos.state.tx.us)
    if (
        domain.endswith(".gov") or domain.endswith(".mil") or domain.endswith(".edu")
        or domain.startswith("sos.")
        or (domain.endswith(".us") and ".state." in domain)
    ):
        return True

    return any(domain == nd or domain.endswith("." + nd) for nd in noise_domains)


def search_keyword(keyword: str) -> list[SERPResult]:
    """Call Serper for one keyword, return up to ~30 organic results (≈3 pages)."""
    if not config.SERPER_API_KEY:
        raise ValueError("SERPER_API_KEY is not set in .env")

    payload = {
        "q": keyword,
        "gl": "us",    # Google US results
        "hl": "en",
        "num": 30,     # ~3 result pages per keyword
    }
    headers = {
        "X-API-KEY": config.SERPER_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(SERPER_ENDPOINT, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [Serper] Request failed for '{keyword}': {e}")
        return []

    data = resp.json()
    results = []
    for item in data.get("organic", []):
        results.append(SERPResult(
            position=item.get("position", 999),
            title=item.get("title", ""),
            link=item.get("link", ""),
            snippet=item.get("snippet", ""),
            keyword=keyword,
        ))
    return results


def search_all_keywords(keywords: list[str]) -> dict[str, list[SERPResult]]:
    """Search all keywords with a small delay between calls. Returns {keyword: [results]}."""
    all_results: dict[str, list[SERPResult]] = {}
    total = len(keywords)
    for i, kw in enumerate(keywords, 1):
        print(f"  [{i}/{total}] Searching: {kw}")
        all_results[kw] = search_keyword(kw)
        if i < total:
            time.sleep(0.5)  # be gentle with the API
    return all_results


def aggregate_competitors(
    all_results: dict[str, list[SERPResult]],
    max_competitors: int = 50,
) -> list[CompetitorSERP]:
    """
    Merge results across all keywords into a deduplicated list of CompetitorSERP
    objects, sorted by average SERP position (best-ranked first).
    """
    domain_map: dict[str, CompetitorSERP] = {}

    for keyword, results in all_results.items():
        for r in results:
            if not r.link or _is_noise(r.link):
                continue
            domain = _extract_domain(r.link)
            if not domain:
                continue
            if domain not in domain_map:
                domain_map[domain] = CompetitorSERP(domain=domain, url=r.link)
            comp = domain_map[domain]
            if keyword not in comp.keywords:
                comp.keywords.append(keyword)
            comp.positions.append(r.position)

    sorted_comps = sorted(domain_map.values(), key=lambda c: (c.avg_position, c.best_position))
    return sorted_comps[:max_competitors]


def build_keyword_summary(
    all_results: dict[str, list[SERPResult]],
) -> list[dict]:
    """Returns per-keyword stats for the Keywords Summary sheet tab."""
    rows = []
    for kw, results in all_results.items():
        valid = [r for r in results if not _is_noise(r.link)]
        rows.append({
            "keyword": kw,
            "total_urls": len(valid),
            "top_competitor": valid[0].link if valid else "",
            "unique_competitors": len({_extract_domain(r.link) for r in valid}),
        })
    return rows
