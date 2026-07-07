"""
generate_opportunities.py

Fetches all tabs of the competitor analysis Google Sheet (public),
passes the raw data to Claude via OpenRouter, and writes
PAGE_AND_FEATURE_OPPORTUNITIES.md with page and feature recommendations.

Usage:
    python3 generate_opportunities.py
"""

import csv
import io
import json
import re
import sys
from datetime import datetime

import requests

import config  # loads .env; exposes OPENROUTER_API_KEY, OPENROUTER_MODEL

# ── Config ─────────────────────────────────────────────────────────────────────

SHEET_ID = "14BvRLM--TpAkwVKZvdIhs57bdOHDm_7syNlLgmj8vog"
OUTPUT_FILE = "PAGE_AND_FEATURE_OPPORTUNITIES.md"
MAX_ROWS_PER_TAB = 150  # cap to keep prompt within model context

BUSINESS_CONTEXT = """
BUSINESS CONTEXT (DocSeal USA):
- Live service today: FBI Background Check (PCC) Apostille — Standard $175, Rush $225, Same Day $275
- Target audience: Indian NRIs in India who need US federal documents apostilled for OCI applications,
  Canada PR/citizenship, UAE/Gulf employment, or other international use cases
- Coming Soon (not yet live, referenced in footer/forms): Birth Certificate Apostille,
  Degree/Transcript Apostille, Marriage Certificate Apostille, Divorce Decree Apostille,
  Naturalization Certificate Apostille
- Currently missing from the site: blog, city-specific landing pages, country/use-case landing pages,
  pricing calculator, document eligibility checker, order tracking portal
- Service model: fully remote/courier-based — no physical office required by client
""".strip()

PROMPT_INSTRUCTIONS = """
Based on the competitor data above (all tabs of the Google Sheet), write a complete
PAGE_AND_FEATURE_OPPORTUNITIES.md file for DocSeal USA.

Requirements:
- Ground every recommendation in what the spreadsheet data actually shows — cite competitor
  names (e.g. apostilleservice.co.in, nriway.com) and specific observations from the sheet
- Tie every page and feature back to the current live business (FBI PCC apostille)
- Separate what's buildable NOW (FBI PCC is live) from what's prep for future services

The file must have exactly these sections:

# DocSeal USA — Page & Feature Opportunities
*Based on [N]-competitor analysis, [current date]*

## Context
(3-5 bullet points: business snapshot + the 3-4 biggest patterns you see across competitors
that create opportunities — be specific, e.g. "14/21 competitors hide pricing...")

## Part 1 — Pages to add (buildable now, FBI PCC is already live)
For each page:
### Px. `/route-slug`
**Why:** (1-2 sentences grounded in competitor data)
**Targets:** (specific keyword phrases from the sheet)
**Content sections:** (bulleted list of concrete headings/sections the page should have)

## Part 2 — Pages to prep for future services (Coming Soon, write now to rank early)
Table: | Page | Target keyword(s) | Priority |
Plus a content template description that applies to all future-service pages.

## Part 3 — Features (not pages)
Table: | Feature | Seen at | Why it matters | Build priority |

## Part 4 — Priority order
Ordered numbered list, grouped by: "Builds bookings now", "Builds authority",
"Reduces support load", "Captures future-service demand", "Long-term differentiation"

Write the complete markdown file content and nothing else — no preamble, no explanation.
""".strip()


# ── Sheet fetching ─────────────────────────────────────────────────────────────

def get_all_tabs(sheet_id: str) -> dict[str, int]:
    """
    Fetch the HTML view of a public Google Sheet and extract {tab_name: gid}.
    Falls back to known gids from config.TAB_NAMES if HTML parsing yields nothing.
    """
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/htmlview"
    try:
        resp = requests.get(url, allow_redirects=True, timeout=30)
        html = resp.text

        tabs: dict[str, int] = {}

        # Pattern 1: "sheetId":NNNN ... "title":"Name"  (same JSON object, any order)
        for m in re.finditer(r'"sheetId":\s*(\d+)', html):
            gid = int(m.group(1))
            # look for the nearest "title" within 200 chars after sheetId
            nearby = html[m.start(): m.start() + 200]
            title_m = re.search(r'"title":\s*"([^"]+)"', nearby)
            if title_m:
                tabs[title_m.group(1)] = gid

        # Pattern 2: "title":"Name" ... "sheetId":NNNN
        if not tabs:
            for m in re.finditer(r'"title":\s*"([^"]+)"[^}]{0,200}"sheetId":\s*(\d+)', html):
                tabs[m.group(1)] = int(m.group(2))

        if tabs:
            return tabs

    except Exception as e:
        print(f"  [warn] HTML tab discovery failed: {e}")

    # Fallback — known gids the user has shared in this session
    print("  [fallback] Using known gid list from session")
    return {
        "Competitor Analysis": 1994625005,
        "Keywords Summary":    1358594671,
    }


def fetch_tab_csv(sheet_id: str, gid: int) -> list[list[str]]:
    """Fetch a single tab as a list of rows. Returns [] on failure."""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    try:
        resp = requests.get(url, allow_redirects=True, timeout=30)
        if resp.status_code != 200:
            return []
        rows = list(csv.reader(io.StringIO(resp.text)))
        return rows
    except Exception as e:
        print(f"  [warn] Failed to fetch gid={gid}: {e}")
        return []


# ── Prompt building ────────────────────────────────────────────────────────────

def rows_to_markdown_table(rows: list[list[str]]) -> str:
    """Convert CSV rows to a simple pipe-delimited markdown table."""
    if not rows:
        return "(empty)"
    # Normalize column count
    width = max(len(r) for r in rows)
    lines = []
    for i, row in enumerate(rows):
        padded = row + [""] * (width - len(row))
        line = "| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in padded) + " |"
        lines.append(line)
        if i == 0:  # header separator
            lines.append("| " + " | ".join(["---"] * width) + " |")
    return "\n".join(lines)


def build_prompt(tabs_data: dict[str, list[list[str]]]) -> str:
    parts = [BUSINESS_CONTEXT, ""]

    for tab_name, rows in tabs_data.items():
        if not rows:
            continue
        truncated = rows[: MAX_ROWS_PER_TAB + 1]  # +1 for header
        note = ""
        if len(rows) > MAX_ROWS_PER_TAB + 1:
            note = f" (showing first {MAX_ROWS_PER_TAB} of {len(rows)-1} data rows)"
        parts.append(f"## Sheet tab: {tab_name}{note}")
        parts.append(rows_to_markdown_table(truncated))
        parts.append("")

    parts.append(PROMPT_INSTRUCTIONS)
    return "\n".join(parts)


# ── OpenRouter call ────────────────────────────────────────────────────────────

def call_openrouter(prompt: str) -> str:
    if not config.OPENROUTER_API_KEY:
        sys.exit("Error: OPENROUTER_API_KEY not set in .env")

    print(f"  Calling {config.OPENROUTER_MODEL} via OpenRouter…")
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": config.OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 8000,
        },
        timeout=180,
    )

    if resp.status_code != 200:
        sys.exit(f"Error: OpenRouter returned {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        sys.exit(f"Error: Unexpected OpenRouter response shape: {json.dumps(data)[:400]}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[1/4] Discovering tabs in sheet {SHEET_ID}…")
    tabs = get_all_tabs(SHEET_ID)
    if not tabs:
        sys.exit("Error: Could not discover any tabs. Make sure the sheet is set to 'Anyone with the link can view'.")
    print(f"      Found {len(tabs)} tab(s): {', '.join(tabs.keys())}")

    print("[2/4] Fetching CSV data for each tab…")
    tabs_data: dict[str, list[list[str]]] = {}
    for name, gid in tabs.items():
        print(f"      → {name} (gid={gid})…", end=" ", flush=True)
        rows = fetch_tab_csv(SHEET_ID, gid)
        if len(rows) < 2:
            print("skipped (empty or unreachable)")
            continue
        tabs_data[name] = rows
        print(f"{len(rows)-1} rows")

    if not tabs_data:
        sys.exit("Error: All tabs came back empty. Is the sheet publicly accessible?")

    print("[3/4] Building prompt and calling OpenRouter…")
    prompt = build_prompt(tabs_data)
    markdown = call_openrouter(prompt)

    print(f"[4/4] Writing {OUTPUT_FILE}…")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"\nDone. {OUTPUT_FILE} updated at {datetime.now().strftime('%Y-%m-%d %H:%M')}.")
    print(f"      ({len(markdown):,} characters written)")


if __name__ == "__main__":
    main()
