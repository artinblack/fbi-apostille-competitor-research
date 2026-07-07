#!/usr/bin/env python3
"""
Stage 1 of the deep pipeline — METERED (spends OpenRouter credits on Perplexity Sonar).

Runs SERP search to locate the target competitors (config.AI_ANALYSIS_DOMAINS), then for each:
multi-page scrape + Sonar web research → output/research/<domain>.md.

Stop after this and hand the bundles to the synthesis stage (Claude Code / Opus writes
output/ai_synthesis.json), then run:
  python3 main.py --ai-from-json output/ai_synthesis.json --reviews --social --no-screenshots

Usage:
  python3 deep_research.py
"""

import sys

import config
from src import serper_client, researcher


def main() -> None:
    if not config.SERPER_API_KEY:
        sys.exit("SERPER_API_KEY not set in .env")
    if not config.OPENROUTER_API_KEY:
        sys.exit("OPENROUTER_API_KEY not set in .env — required for Sonar research")

    targets = set(config.AI_ANALYSIS_DOMAINS)
    print("\n" + "═" * 60)
    print("  FBI Apostille — DEEP RESEARCH (Stage 1, metered)")
    print(f"  Research model : {config.RESEARCH_MODEL}")
    print(f"  Targets        : {len(targets)} competitors")
    print("═" * 60 + "\n")

    print("STEP 1 — Locating target competitors via Serper…")
    serp_results = serper_client.search_all_keywords(config.KEYWORDS)
    competitors = serper_client.aggregate_competitors(
        serp_results, max_competitors=config.MAX_COMPETITORS
    )
    selected = [c for c in competitors if c.domain in targets]
    found = {c.domain for c in selected}
    missing = targets - found

    print(f"  Found {len(selected)}/{len(targets)} targets in SERP results.")
    for c in selected:
        print(f"    • {c.domain}  (avg pos={c.avg_position}, in {c.keyword_count} keyword(s))")
    if missing:
        # Fall back to a bare CompetitorSERP so we still research a named target
        # that didn't surface in this SERP snapshot.
        print(f"  Not in SERP snapshot (will research homepage only): {', '.join(sorted(missing))}")
        for domain in sorted(missing):
            selected.append(serper_client.CompetitorSERP(domain=domain, url=f"https://{domain}/"))
    print()

    print("STEP 2 — Multi-page scrape + Sonar research per competitor…\n")
    for i, comp in enumerate(selected, 1):
        print(f"[{i}/{len(selected)}]")
        researcher.research_competitor(comp)
        print()

    print("═" * 60)
    print("  STAGE 1 COMPLETE")
    print(f"  Bundles written to: output/research/*.md ({len(selected)} files)")
    print("  Next: synthesis (Claude Code writes output/ai_synthesis.json), then")
    print("  python3 main.py --ai-from-json output/ai_synthesis.json --reviews --social --no-screenshots")
    print("═" * 60 + "\n")


if __name__ == "__main__":
    main()
