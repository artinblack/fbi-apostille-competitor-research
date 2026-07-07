"""
Google PageSpeed Insights API — free, no key needed for low-volume use.
Returns Core Web Vitals + mobile/desktop scores for each competitor URL.
Rate limit: ~25 requests / 100 seconds on the keyless tier.
"""

import time
import requests
from dataclasses import dataclass


PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
_DELAY_BETWEEN_CALLS = 5  # seconds — stay within free rate limit


@dataclass
class SpeedData:
    url: str
    mobile_score: int = -1       # 0–100
    desktop_score: int = -1
    fcp_ms: int = -1             # First Contentful Paint
    lcp_ms: int = -1             # Largest Contentful Paint
    tbt_ms: int = -1             # Total Blocking Time
    cls_score: float = -1.0      # Cumulative Layout Shift
    ttfb_ms: int = -1            # Time to First Byte
    speed_grade: str = ""        # "Fast" / "Moderate" / "Slow"
    error: str = ""


def _score_grade(score: int) -> str:
    if score >= 90:
        return "Fast"
    if score >= 50:
        return "Moderate"
    return "Slow"


def _fetch(url: str, strategy: str) -> dict:
    params = {"url": url, "strategy": strategy, "category": "performance"}
    resp = requests.get(PSI_ENDPOINT, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _extract_metric(categories: dict, key: str, field: str = "numericValue") -> int:
    try:
        return int(categories["audits"][key][field])
    except Exception:
        return -1


def audit(url: str) -> SpeedData:
    """Run PageSpeed Insights for mobile and desktop. Returns SpeedData."""
    try:
        mobile_data = _fetch(url, "mobile")
        time.sleep(2)
        desktop_data = _fetch(url, "desktop")
    except requests.RequestException as e:
        return SpeedData(url=url, error=str(e))

    try:
        mobile_score = int(
            mobile_data.get("lighthouseResult", {})
            .get("categories", {})
            .get("performance", {})
            .get("score", -1) * 100
        )
    except Exception:
        mobile_score = -1

    try:
        desktop_score = int(
            desktop_data.get("lighthouseResult", {})
            .get("categories", {})
            .get("performance", {})
            .get("score", -1) * 100
        )
    except Exception:
        desktop_score = -1

    audits = mobile_data.get("lighthouseResult", {}).get("audits", {})

    def _m(key: str) -> int:
        try:
            return int(audits[key]["numericValue"])
        except Exception:
            return -1

    return SpeedData(
        url=url,
        mobile_score=mobile_score,
        desktop_score=desktop_score,
        fcp_ms=_m("first-contentful-paint"),
        lcp_ms=_m("largest-contentful-paint"),
        tbt_ms=_m("total-blocking-time"),
        cls_score=round(float(audits.get("cumulative-layout-shift", {}).get("numericValue", -1)), 3),
        ttfb_ms=_m("server-response-time"),
        speed_grade=_score_grade(mobile_score),
    )


def audit_all(competitors: list, delay: float = _DELAY_BETWEEN_CALLS) -> dict[str, SpeedData]:
    """Audit all competitors. Returns {url: SpeedData}."""
    results: dict[str, SpeedData] = {}
    total = len(competitors)
    for i, comp in enumerate(competitors, 1):
        print(f"  [{i}/{total}] PageSpeed: {comp.domain}")
        results[comp.url] = audit(comp.url)
        s = results[comp.url]
        if s.error:
            print(f"    ✗ {s.error}")
        else:
            print(f"    ✓ Mobile={s.mobile_score} Desktop={s.desktop_score} Grade={s.speed_grade}")
        if i < total:
            time.sleep(delay)
    return results
