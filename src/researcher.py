"""
Deep-research module (Stage 1 of the deep pipeline).

For a single competitor it:
  1. discovers key pages (home, ranking URL, pricing/process pages via Serper site: search),
  2. scrapes them all (Firecrawl + cache, via scraper.scrape),
  3. runs a live web-research pass with Perplexity Sonar (config.RESEARCH_MODEL) over OpenRouter,
and writes a combined research bundle to output/research/<domain>.md.

The bundle is what the synthesis stage (Claude Code / Opus) reads to write the sheet cells.
No JSON schema is enforced here — this stage only *gathers* signal.
"""

import time
from pathlib import Path

import requests

import config
from src import scraper, serper_client


OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
RESEARCH_DIR = Path("output/research")

_MAX_PAGES = 5
_SONAR_MAX_TOKENS = 1200


# ── Page discovery ──────────────────────────────────────────────────────────────

def discover_pages(domain: str, ranking_url: str) -> list[str]:
    """Return up to _MAX_PAGES key URLs for a competitor: home + ranking URL + Serper site: hits."""
    urls: list[str] = [f"https://{domain}/"]
    if ranking_url:
        urls.append(ranking_url)

    site_queries = [
        f"site:{domain} fbi apostille pricing cost",
        f"site:{domain} fbi apostille process turnaround",
    ]
    for q in site_queries:
        try:
            results = serper_client.search_keyword(q)
        except Exception as e:
            print(f"    [discover] Serper failed for '{q}': {e}")
            results = []
        for r in results[:2]:
            if r.link:
                urls.append(r.link)
        time.sleep(0.4)

    # Dedupe preserving order, cap at _MAX_PAGES
    seen: set[str] = set()
    deduped: list[str] = []
    for u in urls:
        key = u.rstrip("/")
        if key not in seen:
            seen.add(key)
            deduped.append(u)
    return deduped[:_MAX_PAGES]


def multipage_scrape(urls: list[str]) -> str:
    """Scrape each URL (cached) and return a single labelled, concatenated markdown blob."""
    parts: list[str] = []
    for u in urls:
        scraped = scraper.scrape(u)
        status = scraped.scrape_method
        md = (scraped.markdown or "").strip()
        if not md or status == "failed":
            parts.append(f"### PAGE: {u}\n[scrape failed]\n")
            continue
        # Cap each page so one huge page doesn't crowd out the others
        parts.append(f"### PAGE: {u}  (title: {scraped.title or 'n/a'}, via {status})\n\n{md[:5000]}\n")
        time.sleep(config.REQUEST_DELAY)
    return "\n\n".join(parts)


# ── Sonar web research ──────────────────────────────────────────────────────────

_SONAR_PROMPT = """\
You are a market researcher investigating a US-based FBI background-check apostille service.
Research the company at the domain "{domain}" using current web sources.

Report concise, factual findings (with sources) on:
1. Reputation and customer review sentiment — common praises and common complaints.
2. Publicly stated or reported pricing, fees, and turnaround/processing times.
3. What documents/services they handle and their key differentiators.
4. Who their target customers appear to be (destination countries, use cases).
5. How they compare to other FBI apostille services (strengths and weaknesses).

If information is not publicly available, say so explicitly rather than guessing.
Keep it under ~400 words. End with a "Sources:" list of the URLs you used."""


def sonar_research(domain: str) -> tuple[str, list[str]]:
    """Run one Perplexity Sonar research call over OpenRouter. Returns (findings_text, citations)."""
    if not config.OPENROUTER_API_KEY:
        return "[OPENROUTER_API_KEY not set — Sonar research skipped]", []

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://fbi-apostille-research",
        "X-Title": "FBI Apostille Deep Research",
    }
    payload = {
        "model": config.RESEARCH_MODEL,
        "messages": [{"role": "user", "content": _SONAR_PROMPT.format(domain=domain)}],
        "temperature": 0.2,
        "max_tokens": _SONAR_MAX_TOKENS,
    }

    try:
        resp = requests.post(OPENROUTER_ENDPOINT, json=payload, headers=headers, timeout=90)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return f"[Sonar request failed: {e}]", []

    text = data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
    # OpenRouter surfaces Perplexity citations at the top level of the response.
    citations = data.get("citations") or []
    if not citations:
        # Some responses nest citations on the message.
        citations = data.get("choices", [{}])[0].get("message", {}).get("citations", []) or []
    return text, citations


# ── Bundle one competitor ───────────────────────────────────────────────────────

def research_competitor(comp) -> dict:
    """Full Stage-1 research for one CompetitorSERP. Writes output/research/<domain>.md."""
    domain = comp.domain
    print(f"  Researching {domain} …")

    urls = discover_pages(domain, comp.url)
    print(f"    Pages: {len(urls)} → {', '.join(urls)}")
    scraped_md = multipage_scrape(urls)

    print(f"    Sonar research via {config.RESEARCH_MODEL} …")
    findings, citations = sonar_research(domain)

    bundle = {
        "domain": domain,
        "ranking_url": comp.url,
        "keywords_found_in": list(comp.keywords),
        "best_position": comp.best_position,
        "avg_position": comp.avg_position,
        "urls": urls,
        "scraped_markdown": scraped_md,
        "sonar_findings": findings,
        "citations": citations,
    }

    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    out = RESEARCH_DIR / f"{domain}.md"
    cite_block = "\n".join(f"- {c}" for c in citations) if citations else "(none returned)"
    out.write_text(
        f"# Research bundle — {domain}\n\n"
        f"- Ranking URL: {comp.url}\n"
        f"- Keywords ranked for: {', '.join(comp.keywords)}\n"
        f"- Best SERP position: {comp.best_position} | Avg: {comp.avg_position}\n"
        f"- Pages scraped: {', '.join(urls)}\n\n"
        f"## Sonar web research ({config.RESEARCH_MODEL})\n\n{findings}\n\n"
        f"### Citations\n{cite_block}\n\n"
        f"## Scraped site content (multi-page)\n\n{scraped_md}\n",
        encoding="utf-8",
    )
    print(f"    ✓ Bundle → {out}")
    return bundle
