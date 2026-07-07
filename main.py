#!/usr/bin/env python3
"""
FBI Apostille Competitor Research Automation
─────────────────────────────────────────
Searches Google US for FBI-apostille keywords via Serper, scrapes the
top competitor websites via Firecrawl, analyses them with an OpenRouter AI
model, and writes everything to a Google Sheet + local CSV backup.

Usage:
  python main.py                       # Full run
  python main.py --limit 5             # Process only first 5 competitors
  python main.py --keywords-only       # SERP search only, no scrape/AI
  python main.py --skip-ai             # Scrape but skip OpenRouter analysis
  python main.py --resume              # Skip URLs already in today's progress file
  python main.py --dry-run             # Full run but skip CSV/Sheets writes (for testing)
  python main.py --no-screenshots      # Skip Playwright screenshot capture
  python main.py --pagespeed           # Add PageSpeed Insights step
  python main.py --reviews             # Add Trustpilot + Google Places step
  python main.py --pricing             # Add AI pricing extraction step
  python main.py --content-gaps        # Add FBI-apostille content gap analysis step
  python main.py --social              # Add social media + ads detection step
  python main.py --all-extras          # Enable all extra analysis modules
  python main.py --notify              # Send Slack/email completion notification
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit("Python 3.10+ is required.")

import config
from src import serper_client, scraper, analyzer, sheets_client


OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

TODAY = datetime.now().strftime("%Y-%m-%d")
PROGRESS_FILE = OUTPUT_DIR / f"progress_{TODAY}.json"
CSV_FILE = OUTPUT_DIR / f"results_{TODAY}.csv"


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Apostille competitor research tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--limit",         type=int,  default=None, metavar="N",
                   help="Process only the first N unique competitors")
    p.add_argument("--keywords-only", action="store_true",
                   help="Only run SERP search; skip scraping and AI analysis")
    p.add_argument("--skip-ai",       action="store_true",
                   help="Scrape websites but skip OpenRouter AI analysis")
    p.add_argument("--ai-from-json",  type=str, default=None, metavar="PATH",
                   help="Load hand-written AI synthesis (analysis/pricing/content-gaps) from a JSON "
                        "file instead of calling OpenRouter. Fills those tabs for the domains present.")
    p.add_argument("--resume",        action="store_true",
                   help="Skip URLs already present in today's progress file")
    p.add_argument("--dry-run",       action="store_true",
                   help="Run all analysis but skip writing CSV and Google Sheets")
    p.add_argument("--no-screenshots", action="store_true",
                   help="Skip Playwright screenshot capture")
    p.add_argument("--pagespeed",     action="store_true",
                   help="Run Google PageSpeed Insights for each competitor")
    p.add_argument("--reviews",       action="store_true",
                   help="Scrape Google Places + Trustpilot review data")
    p.add_argument("--pricing",       action="store_true",
                   help="Run AI-powered pricing extraction")
    p.add_argument("--content-gaps",  action="store_true",
                   help="Run FBI-apostille content gap analysis")
    p.add_argument("--social",        action="store_true",
                   help="Detect social media profiles + Google Ads activity")
    p.add_argument("--all-extras",    action="store_true",
                   help="Enable ALL extra analysis modules (pagespeed, reviews, pricing, content-gaps, social)")
    p.add_argument("--notify",        action="store_true",
                   help="Send Slack/email notification when run completes")
    return p.parse_args()


# ── Progress tracking ─────────────────────────────────────────────────────────

def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text())
        except Exception:
            pass
    return {}


def save_progress(progress: dict) -> None:
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2))


# ── CSV backup ────────────────────────────────────────────────────────────────

def save_csv(rows: list[dict]) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  CSV saved → {CSV_FILE}")


# ── Validation ────────────────────────────────────────────────────────────────

def _check_env(args) -> bool:
    ok = True
    if not config.SERPER_API_KEY:
        print("  ERROR: SERPER_API_KEY not set in .env")
        ok = False
    if not args.keywords_only and not config.FIRECRAWL_API_KEY:
        print("  WARNING: FIRECRAWL_API_KEY not set — Jina fallback will be used for all sites")
    if not args.keywords_only and not args.skip_ai and not args.ai_from_json and not config.OPENROUTER_API_KEY:
        print("  ERROR: OPENROUTER_API_KEY not set in .env")
        ok = False
    oauth_path = os.getenv("OAUTH_CREDENTIALS_PATH", "credentials.json")
    token_path = os.path.expanduser("~/.config/gspread/authorized_user.json")
    if not os.path.exists(oauth_path) and not os.path.exists(token_path):
        print(f"  WARNING: OAuth credentials not found at {oauth_path} — Sheets write will be skipped")
    return ok


# ── AI synthesis from JSON ──────────────────────────────────────────────────────

def _build_ai_maps_from_json(path: str, competitors) -> tuple[dict, dict, dict]:
    """Build analysis/pricing/content-gap maps (keyed by competitor URL) from a synthesis JSON.

    JSON shape: { "<domain>": { "analysis": {...}, "pricing": {...}, "content_gap": {...} }, ... }
    Fields map 1:1 to AnalysisResult / PricingData / ContentGapData.
    """
    from src.analyzer import AnalysisResult
    from src.pricing_extractor import PricingData
    from src.content_gap import ContentGapData

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    domain_to_url = {c.domain: c.url for c in competitors}
    analysis_map: dict = {}
    pricing_map: dict = {}
    gap_map: dict = {}

    for domain, blocks in data.items():
        url = domain_to_url.get(domain)
        if not url:
            print(f"  [ai-from-json] '{domain}' not among current competitors — skipped")
            continue

        a = blocks.get("analysis") or {}
        if a:
            analysis_map[url] = AnalysisResult(
                marketing_strategy=a.get("marketing_strategy", ""),
                primary_offer=a.get("primary_offer", ""),
                key_headlines=a.get("key_headlines", []) or [],
                value_proposition=a.get("value_proposition", ""),
                pricing_transparency=a.get("pricing_transparency", ""),
                social_proof=a.get("social_proof", ""),
                trust_signals=a.get("trust_signals", ""),
                cold_email_signals=a.get("cold_email_signals", ""),
                form_analysis=a.get("form_analysis", ""),
                content_marketing=a.get("content_marketing", ""),
                workflow_logic=a.get("workflow_logic", ""),
                what_to_learn=a.get("what_to_learn", ""),
                what_to_improve=a.get("what_to_improve", ""),
                our_competitive_advantage=a.get("our_competitive_advantage", ""),
                future_ideas=a.get("future_ideas", ""),
            )

        p = blocks.get("pricing") or {}
        if p:
            pricing_map[url] = PricingData(
                url=url,
                has_pricing=bool(p.get("has_pricing", False)),
                pricing_model=p.get("pricing_model", ""),
                currency=p.get("currency", ""),
                packages=p.get("packages", []) or [],
                document_prices=p.get("document_prices", {}) or {},
                government_fee_included=p.get("government_fee_included"),
                shipping_fee=p.get("shipping_fee", ""),
                free_services=p.get("free_services", []) or [],
                pricing_transparency_score=int(p.get("pricing_transparency_score", 0) or 0),
                notes=p.get("notes", ""),
            )

        g = blocks.get("content_gap") or {}
        if g:
            cg = ContentGapData(
                url=url,
                content_depth=g.get("content_depth", ""),
                has_country_guides=bool(g.get("has_country_guides", False)),
                has_faq=bool(g.get("has_faq", False)),
                has_process_explainer=bool(g.get("has_process_explainer", False)),
                has_state_specific_guides=bool(g.get("has_state_specific_guides", False)),
                has_video_content=bool(g.get("has_video_content", False)),
                blog_post_count_estimate=int(g.get("blog_post_count_estimate", 0) or 0),
                gaps_identified=g.get("gaps_identified", []) or [],
                document_coverage=g.get("document_coverage", {}) or {},
                use_case_coverage=g.get("use_case_coverage", {}) or {},
            )
            cg.coverage_score = int(g.get("coverage_score", 0) or 0)
            gap_map[url] = cg

    return analysis_map, pricing_map, gap_map


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    # --all-extras enables all extra modules
    if args.all_extras:
        args.pagespeed   = True
        args.reviews     = True
        args.pricing     = True
        args.content_gaps = True
        args.social      = True

    print("\n" + "═" * 60)
    print("  Apostille Competitor Research — starting run")
    print(f"  Date     : {TODAY}")
    print(f"  Model    : {config.OPENROUTER_MODEL}")
    if args.dry_run:
        print("  Mode     : DRY RUN (no CSV / Sheets writes)")
    extras = [f for f, v in [
        ("pagespeed", args.pagespeed), ("reviews", args.reviews),
        ("pricing", args.pricing), ("content-gaps", args.content_gaps),
        ("social", args.social),
    ] if v]
    if extras:
        print(f"  Extras   : {', '.join(extras)}")
    print("═" * 60 + "\n")

    if not _check_env(args):
        sys.exit(1)

    # ── STEP 1: Keyword search ────────────────────────────────────────────────
    print("STEP 1 — Searching keywords via Serper…")
    serp_results = serper_client.search_all_keywords(config.KEYWORDS)
    print(f"  Done. {sum(len(v) for v in serp_results.values())} total SERP results across {len(config.KEYWORDS)} keywords.\n")

    # ── STEP 2: Aggregate competitors ─────────────────────────────────────────
    competitors = serper_client.aggregate_competitors(
        serp_results, max_competitors=config.MAX_COMPETITORS
    )
    keyword_summary = serper_client.build_keyword_summary(serp_results)

    limit = args.limit or len(competitors)
    competitors = competitors[:limit]

    print(f"STEP 2 — {len(competitors)} unique competitors identified (limit={limit}):")
    for i, c in enumerate(competitors, 1):
        print(f"  {i:>2}. {c.domain}  (avg pos={c.avg_position}, in {c.keyword_count} keyword(s))")
    print()

    if args.keywords_only:
        print("--keywords-only flag set — skipping scrape and AI analysis.\n")
        _finish(competitors, {}, {}, keyword_summary, serp_results, "", args)
        return

    # ── STEP 3: Scrape websites ───────────────────────────────────────────────
    print("STEP 3 — Scraping competitor websites…")
    progress = load_progress() if args.resume else {}
    scraped_map: dict = {}

    for i, comp in enumerate(competitors, 1):
        url = comp.url
        print(f"  [{i}/{len(competitors)}] {url}")
        scraped_map[url] = scraper.scrape(url)
        progress.setdefault("scraped", {})[url] = True
        save_progress(progress)
        if i < len(competitors):
            time.sleep(config.REQUEST_DELAY)

    succeeded = sum(1 for s in scraped_map.values() if s.scrape_method != "failed")
    print(f"  Scraping complete. {succeeded}/{len(competitors)} succeeded.\n")

    # ── STEP 4: AI analysis ───────────────────────────────────────────────────
    # --skip-ai skips ONLY the OpenRouter analysis + insights; non-AI extras
    # (reviews, social) below still run. --ai-from-json injects hand-written
    # synthesis instead of calling OpenRouter.
    analysis_map: dict = {}
    json_pricing_map: dict = {}
    json_gap_map: dict = {}
    if args.ai_from_json:
        print(f"--ai-from-json set — loading synthesis from {args.ai_from_json} (no OpenRouter calls).")
        analysis_map, json_pricing_map, json_gap_map = _build_ai_maps_from_json(
            args.ai_from_json, competitors
        )
        print(f"  Loaded AI content for {len(analysis_map)} competitor(s).\n")
    elif args.skip_ai:
        print("--skip-ai flag set — skipping OpenRouter analysis (STEP 4/5).\n")
    else:
        print("STEP 4 — Analysing competitors with AI…")
        for i, comp in enumerate(competitors, 1):
            url = comp.url
            scraped = scraped_map.get(url)
            print(f"  [{i}/{len(competitors)}] {comp.domain}")

            if scraped and scraped.scrape_method != "failed":
                analysis_map[url] = analyzer.analyze(url, scraped, comp)
                err = analysis_map[url].error
                if err:
                    print(f"    ✗ AI error: {err}")
                else:
                    print(f"    ✓ Analysis complete")
            else:
                print(f"    – skipped (scrape failed)")

            progress.setdefault("analyzed", {})[url] = True
            save_progress(progress)

        ai_ok = sum(1 for a in analysis_map.values() if not a.error)
        print(f"  AI analysis complete. {ai_ok}/{len(competitors)} succeeded.\n")

    # ── STEP 5: Insights Dashboard ────────────────────────────────────────────
    insights_text = ""
    if not args.skip_ai and not args.ai_from_json:
        print("STEP 5 — Generating overall Insights Dashboard…")
        valid_analyses = [(url, ar) for url, ar in analysis_map.items() if not ar.error]
        insights_text = analyzer.generate_insights_summary(valid_analyses)
        print("  Insights generated.\n")

    # ── STEP 6: Extra analysis modules ───────────────────────────────────────
    pricing_map   = None
    reviews_map   = None
    gap_map       = None
    speed_map     = None
    social_map    = None
    step = 6

    if args.ai_from_json:
        # Pricing + content-gaps come from the synthesis JSON, not the extractors.
        pricing_map = json_pricing_map or None
        gap_map = json_gap_map or None
    elif args.pricing:
        step += 1
        print(f"STEP {step} — Extracting pricing intelligence…")
        from src import pricing_extractor
        pricing_map = pricing_extractor.extract_all(competitors, scraped_map)
        print()

    if args.reviews:
        step += 1
        print(f"STEP {step} — Scraping reviews & trust data…")
        from src import reviews_scraper
        reviews_map = reviews_scraper.scrape_all(competitors)
        print()

    if args.content_gaps and not args.ai_from_json:
        step += 1
        print(f"STEP {step} — Analysing content gaps…")
        from src import content_gap
        gap_map = content_gap.analyze_all(competitors, scraped_map)
        print()

    if args.pagespeed:
        step += 1
        print(f"STEP {step} — Running PageSpeed Insights…")
        from src import pagespeed
        speed_map = pagespeed.audit_all(competitors)
        print()

    if args.social:
        step += 1
        print(f"STEP {step} — Analysing social media & ads…")
        from src import social_analyzer
        social_map = social_analyzer.analyze_all(competitors, scraped_map)
        print()

    if not args.no_screenshots:
        step += 1
        print(f"STEP {step} — Capturing screenshots…")
        from src import screenshot
        screenshot.capture_all(competitors)
        print()

    # ── STEP N: Write outputs ─────────────────────────────────────────────────
    _finish(
        competitors, scraped_map, analysis_map,
        keyword_summary, serp_results, insights_text, args,
        pricing_map=pricing_map,
        reviews_map=reviews_map,
        gap_map=gap_map,
        speed_map=speed_map,
        social_map=social_map,
    )


def _finish(
    competitors, scraped_map, analysis_map,
    keyword_summary, serp_results, insights_text, args,
    pricing_map=None, reviews_map=None, gap_map=None,
    speed_map=None, social_map=None,
):
    ai_ok    = sum(1 for a in analysis_map.values() if not a.error)
    scrape_ok = sum(1 for s in scraped_map.values() if s.scrape_method != "failed")

    if args.dry_run:
        print("\n[DRY RUN] Skipping CSV and Google Sheets writes.")
    else:
        print("Writing outputs…")

        # CSV backup
        csv_rows = _build_csv_rows(competitors, scraped_map, analysis_map)
        save_csv(csv_rows)

        # Google Sheets
        oauth_path = os.getenv("OAUTH_CREDENTIALS_PATH", "credentials.json")
        token_path = os.path.expanduser("~/.config/gspread/authorized_user.json")
        if os.path.exists(oauth_path) or os.path.exists(token_path):
            sheets_client.write_all(
                competitors=competitors,
                scraped_map=scraped_map,
                analysis_map=analysis_map,
                keyword_summary=keyword_summary,
                serp_results=serp_results,
                insights_text=insights_text,
                pricing_map=pricing_map,
                reviews_map=reviews_map,
                gap_map=gap_map,
                speed_map=speed_map,
                social_map=social_map,
            )
        else:
            print("  [Sheets] Skipped — credentials file not found.")

        # Weekly diff
        try:
            from src import scheduler
            scheduler.run_diff_and_notify(CSV_FILE)
        except Exception as e:
            print(f"  [Diff] Skipped: {e}")

    # Notification
    if args.notify and not args.dry_run:
        try:
            from src import notifier
            notifier.notify_run_complete(
                competitors_count=len(competitors),
                analyses_count=ai_ok,
                csv_path=str(CSV_FILE),
            )
        except Exception as e:
            print(f"  [Notify] Failed: {e}")

    # Summary
    print("\n" + "═" * 60)
    print("  RUN COMPLETE")
    print(f"  Competitors found    : {len(competitors)}")
    print(f"  Scraped successfully : {scrape_ok}")
    print(f"  AI analyses done     : {ai_ok}")
    if not args.dry_run:
        print(f"  CSV backup           : {CSV_FILE}")
    print("═" * 60 + "\n")


def _build_csv_rows(competitors, scraped_map, analysis_map) -> list[dict]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = []
    for rank, comp in enumerate(competitors, 1):
        url = comp.url
        scraped  = scraped_map.get(url)
        analysis = analysis_map.get(url)
        row = {
            "Rank": rank,
            "Domain": comp.domain,
            "URL": url,
            "Keywords Found In": ", ".join(comp.keywords),
            "# Keywords Ranking": comp.keyword_count,
            "Best SERP Position": comp.best_position,
            "Avg SERP Position": comp.avg_position,
            "Scrape Method": scraped.scrape_method if scraped else "",
            "Page Title": scraped.title if scraped else "",
            "Content Signals": _scraper_signals_str(scraped),
            "Marketing Strategy": _safe_field(analysis, "marketing_strategy"),
            "Primary Offer": _safe_field(analysis, "primary_offer"),
            "Key Headlines": _safe_headlines_str(analysis),
            "Value Proposition": _safe_field(analysis, "value_proposition"),
            "Pricing Transparency": _safe_field(analysis, "pricing_transparency"),
            "Social Proof": _safe_field(analysis, "social_proof"),
            "Trust Signals": _safe_field(analysis, "trust_signals"),
            "Cold Email Signals": _safe_field(analysis, "cold_email_signals"),
            "Form Analysis": _safe_field(analysis, "form_analysis"),
            "Content Marketing": _safe_field(analysis, "content_marketing"),
            "Workflow Logic": _safe_field(analysis, "workflow_logic"),
            "What to Learn": _safe_field(analysis, "what_to_learn"),
            "What They Can Improve": _safe_field(analysis, "what_to_improve"),
            "Our Competitive Advantage": _safe_field(analysis, "our_competitive_advantage"),
            "Future Ideas": _safe_field(analysis, "future_ideas"),
            "AI Error": _safe_field(analysis, "error"),
            "Last Analyzed": now,
        }
        rows.append(row)
    return rows


def _safe_field(obj, field: str) -> str:
    if obj is None:
        return ""
    return str(getattr(obj, field, "") or "")


def _safe_headlines_str(analysis) -> str:
    if analysis is None:
        return ""
    return analysis.headlines_str() if hasattr(analysis, "headlines_str") else ""


def _scraper_signals_str(scraped) -> str:
    if scraped is None:
        return ""
    labels = {
        "has_blog": "Blog", "has_testimonials": "Testimonials",
        "has_newsletter": "Newsletter", "has_pricing": "Pricing",
        "has_whatsapp": "WhatsApp", "has_form": "Form",
        "has_live_chat": "Live Chat",
    }
    return ", ".join(lbl for attr, lbl in labels.items() if getattr(scraped, attr, False)) or "None"


if __name__ == "__main__":
    main()
