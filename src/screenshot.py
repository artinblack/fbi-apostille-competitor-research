"""
Browser screenshot archive using Playwright.
Saves full-page screenshots to output/screenshots/ with timestamps.
Install: pip install playwright && playwright install chromium
"""

import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


SCREENSHOT_DIR = Path("output/screenshots")


def _safe_filename(url: str) -> str:
    domain = urlparse(url).netloc.removeprefix("www.")
    return re.sub(r"[^\w\-.]", "_", domain)[:80]


def capture(url: str, full_page: bool = True) -> str:
    """
    Capture a screenshot of url. Returns the saved file path, or empty string on failure.
    Requires playwright to be installed.
    """
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    fname = f"{_safe_filename(url)}_{date_str}.png"
    out_path = SCREENSHOT_DIR / fname

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("    ✗ playwright not installed. Run: pip install playwright && playwright install chromium")
        return ""

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            )
            page = ctx.new_page()
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)  # let JS settle
            page.screenshot(path=str(out_path), full_page=full_page)
            browser.close()
        return str(out_path)
    except Exception as e:
        print(f"    ✗ Screenshot failed for {url}: {e}")
        return ""


def capture_all(competitors: list, delay: float = 3.0) -> dict[str, str]:
    """
    Capture screenshots for all competitors.
    Returns {url: file_path}. Skips if screenshot already exists today.
    """
    results: dict[str, str] = {}
    total = len(competitors)
    date_str = datetime.now().strftime("%Y-%m-%d")

    for i, comp in enumerate(competitors, 1):
        url = comp.url
        fname = f"{_safe_filename(url)}_{date_str}.png"
        existing = SCREENSHOT_DIR / fname

        print(f"  [{i}/{total}] Screenshot: {comp.domain}")

        if existing.exists():
            print(f"    → already captured today, skipping")
            results[url] = str(existing)
        else:
            path = capture(url)
            results[url] = path
            if path:
                print(f"    ✓ Saved: {path}")
            if i < total:
                time.sleep(delay)

    return results
