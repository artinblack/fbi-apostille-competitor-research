"""
Per-domain cache for scraped data.
Stores results in output/cache/ as JSON files with a 7-day TTL.
Prevents re-scraping unchanged sites on re-runs, saving Firecrawl credits.
"""

import json
import os
import time
from dataclasses import asdict
from pathlib import Path


CACHE_DIR = Path("output/cache")
CACHE_TTL_SECONDS = 7 * 24 * 3600  # 7 days


def _cache_path(url: str) -> Path:
    safe = url.replace("https://", "").replace("http://", "").replace("/", "_").replace(":", "_")
    safe = safe[:120]  # cap filename length
    return CACHE_DIR / f"{safe}.json"


def get(url: str) -> dict | None:
    """Return cached data for url if it exists and is not stale. Returns None otherwise."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(url)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if time.time() - data.get("_cached_at", 0) > CACHE_TTL_SECONDS:
            path.unlink(missing_ok=True)
            return None
        return data
    except Exception:
        return None


def set(url: str, data: dict) -> None:
    """Write data to cache for url."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {**data, "_cached_at": time.time()}
    try:
        _cache_path(url).write_text(json.dumps(payload, indent=2))
    except Exception:
        pass


def invalidate(url: str) -> None:
    """Delete cache entry for url."""
    _cache_path(url).unlink(missing_ok=True)


def stats() -> dict:
    """Return cache hit/miss statistics helper (for dry-run)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    files = list(CACHE_DIR.glob("*.json"))
    fresh = sum(
        1 for f in files
        if time.time() - json.loads(f.read_text()).get("_cached_at", 0) <= CACHE_TTL_SECONDS
    )
    return {"total": len(files), "fresh": fresh, "stale": len(files) - fresh}
