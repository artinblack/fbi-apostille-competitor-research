#!/usr/bin/env python3
"""
Generate a detailed plain-text competitor report from the live Google Sheet
(reads all tabs written by main.py) → output/FBI_Apostille_Competitor_Report_<date>.txt
"""

from datetime import datetime
from pathlib import Path

import config
from src import sheets_client


def _rows(ss, tab):
    try:
        return ss.worksheet(tab).get_all_values()
    except Exception as e:
        print(f"  ! could not read tab '{tab}': {e}")
        return []


def _num(x, default=0.0):
    try:
        return float(str(x).replace("★", "").strip())
    except Exception:
        return default


def main():
    ss = sheets_client._connect()
    T = config.TAB_NAMES

    analysis = _rows(ss, T["analysis"])
    keywords = _rows(ss, T["keywords"])
    reviews  = _rows(ss, T["reviews"])
    social   = _rows(ss, T["social"])

    a_hdr, a_data = (analysis[0], analysis[1:]) if analysis else ([], [])
    k_hdr, k_data = (keywords[0], keywords[1:]) if keywords else ([], [])
    r_hdr, r_data = (reviews[0], reviews[1:]) if reviews else ([], [])
    s_hdr, s_data = (social[0], social[1:]) if social else ([], [])

    def col(hdr, name):
        return hdr.index(name) if name in hdr else -1

    out = []
    W = 78
    bar = "=" * W
    dash = "-" * W

    out.append(bar)
    out.append("  FBI APOSTILLE — COMPETITOR ANALYSIS REPORT".center(W))
    out.append(bar)
    out.append(f"  Generated : {datetime.now():%Y-%m-%d %H:%M}")
    out.append(f"  Niche     : US-based FBI background-check apostille services")
    out.append(f"  Locale    : Google US (gl=us), top ~3 result pages per keyword")
    out.append(f"  Keywords  : {len(config.KEYWORDS)} tracked")
    out.append(f"  Sheet     : https://docs.google.com/spreadsheets/d/{config.GOOGLE_SHEET_ID}")
    out.append(f"  Note      : AI columns (marketing strategy, pricing, content gaps) are")
    out.append(f"              blank pending an OpenRouter key — SERP, reviews & social are live.")
    out.append("")

    # ── Executive summary ─────────────────────────────────────────────────────
    out.append(bar)
    out.append("  1. EXECUTIVE SUMMARY")
    out.append(bar)
    out.append(f"  Unique competitor domains analysed : {len(a_data)}")
    ci_best = col(a_hdr, "Best SERP Position")
    ci_kw   = col(a_hdr, "# Keywords Ranking")
    if a_data and ci_best >= 0:
        top3 = [f"{r[1]} (#{r[ci_best]})" for r in a_data[:3] if len(r) > ci_best]
        out.append(f"  Top 3 by SERP rank                 : {', '.join(top3)}")
    if a_data and ci_kw >= 0:
        broad = sorted(a_data, key=lambda r: -_num(r[ci_kw]) if len(r) > ci_kw else 0)[:3]
        out.append(f"  Broadest keyword coverage          : "
                   + ", ".join(f"{r[1]} ({r[ci_kw]} kw)" for r in broad if len(r) > ci_kw))
    out.append("")

    # ── Keyword landscape ─────────────────────────────────────────────────────
    out.append(bar)
    out.append("  2. KEYWORD LANDSCAPE")
    out.append(bar)
    out.append(f"  {'Keyword':<42}{'URLs':>6}{'Uniq':>6}  Top competitor")
    out.append(f"  {dash[:74]}")
    for r in k_data:
        kw = r[0][:40]
        urls = r[1] if len(r) > 1 else ""
        top = r[2] if len(r) > 2 else ""
        uniq = r[3] if len(r) > 3 else ""
        dom = top.split("//")[-1].split("/")[0].replace("www.", "")[:26]
        out.append(f"  {kw:<42}{urls:>6}{uniq:>6}  {dom}")
    out.append("")

    # ── Full competitor ranking ───────────────────────────────────────────────
    out.append(bar)
    out.append("  3. COMPETITOR RANKING (by avg SERP position)")
    out.append(bar)
    ci_avg = col(a_hdr, "Avg SERP Position")
    ci_url = col(a_hdr, "URL")
    ci_kwin = col(a_hdr, "Keywords Found In")
    for r in a_data:
        rank = r[0]
        dom = r[1]
        best = r[ci_best] if ci_best >= 0 and len(r) > ci_best else "?"
        avg = r[ci_avg] if ci_avg >= 0 and len(r) > ci_avg else "?"
        nkw = r[ci_kw] if ci_kw >= 0 and len(r) > ci_kw else "?"
        out.append(f"  #{rank:<3} {dom:<34} best#{best:<3} avg#{avg:<5} {nkw} keyword(s)")
        if ci_url >= 0 and len(r) > ci_url:
            out.append(f"       url : {r[ci_url]}")
        if ci_kwin >= 0 and len(r) > ci_kwin and r[ci_kwin]:
            kws = r[ci_kwin]
            out.append(f"       kw  : {kws[:150]}{'…' if len(kws) > 150 else ''}")
    out.append("")

    # ── Reviews & trust ───────────────────────────────────────────────────────
    out.append(bar)
    out.append("  4. REVIEWS & TRUST (sorted by Google rating × volume)")
    out.append(bar)
    gi_r = col(r_hdr, "Google Rating")
    gi_c = col(r_hdr, "Google Reviews")
    gi_t = col(r_hdr, "Overall Trust Score")
    gi_p = col(r_hdr, "Google Place Name")
    def rev_key(row):
        rt = _num(row[gi_r]) if gi_r >= 0 and len(row) > gi_r else 0
        ct = _num(row[gi_c]) if gi_c >= 0 and len(row) > gi_c else 0
        return -(rt * (ct ** 0.5))
    ranked_reviews = sorted([r for r in r_data if r and r[0]], key=rev_key)
    out.append(f"  {'Domain':<34}{'Rating':>8}{'Reviews':>9}  Trust   Place")
    out.append(f"  {dash[:74]}")
    for r in ranked_reviews:
        dom = r[0][:32]
        rt = r[gi_r] if gi_r >= 0 and len(r) > gi_r and r[gi_r] else "-"
        ct = r[gi_c] if gi_c >= 0 and len(r) > gi_c and r[gi_c] else "-"
        tr = r[gi_t] if gi_t >= 0 and len(r) > gi_t and r[gi_t] else "-"
        pl = (r[gi_p] if gi_p >= 0 and len(r) > gi_p else "")[:22]
        out.append(f"  {dom:<34}{rt:>8}{ct:>9}  {tr:<7} {pl}")
    out.append("")

    # ── Social presence ───────────────────────────────────────────────────────
    out.append(bar)
    out.append("  5. SOCIAL & ADS PRESENCE")
    out.append(bar)
    si_p = col(s_hdr, "Active Platforms")
    si_ads = col(s_hdr, "Running Google Ads")
    with_social = [r for r in s_data if r and len(r) > si_p and r[si_p].strip()]
    ads_running = [r for r in s_data if r and len(r) > si_ads and r[si_ads] == "Yes"]
    out.append(f"  Competitors with detected social profiles : {len(with_social)}/{len(s_data)}")
    out.append(f"  Competitors detected running Google Ads   : {len(ads_running)}/{len(s_data)}")
    out.append("")
    out.append(f"  {'Domain':<34}Active platforms")
    out.append(f"  {dash[:74]}")
    for r in with_social:
        out.append(f"  {r[0][:32]:<34}{r[si_p]}")
    out.append("")

    # ── Observations ──────────────────────────────────────────────────────────
    out.append(bar)
    out.append("  6. OBSERVATIONS")
    out.append(bar)
    obs = [
        "Government Secretary-of-State offices, embassies (.gov) and universities",
        "  (.edu) were filtered out — they issue apostilles but are not competitors.",
        "A small cluster of domains (e.g. broad-coverage sites) rank across many",
        "  keywords — those are the primary SEO competitors to benchmark against.",
        "High-trust competitors (Google 4.9★ with hundreds/thousands of reviews)",
        "  set the review bar; new entrants need a deliberate review-generation plan.",
        "Enable OpenRouter to unlock the AI tabs: per-site marketing strategy, value",
        "  proposition, pricing extraction, and cross-site content-gap opportunities.",
    ]
    for o in obs:
        out.append(f"  - {o}" if not o.startswith("  ") else f"    {o.strip()}")
    out.append("")
    out.append(bar)
    out.append("  END OF REPORT".center(W))
    out.append(bar)

    text = "\n".join(out) + "\n"
    date = datetime.now().strftime("%Y-%m-%d")
    path = Path("output") / f"FBI_Apostille_Competitor_Report_{date}.txt"
    path.write_text(text, encoding="utf-8")
    print(f"Report written → {path}  ({len(a_data)} competitors)")


if __name__ == "__main__":
    main()
