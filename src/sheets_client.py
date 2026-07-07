"""
Google Sheets writer — authenticates via OAuth2 (installed-app flow) and writes
all competitor research data to 4 tabs in the user's fixed Google Sheet.

First run: a browser window opens for one-time Google login. gspread saves a
token to ~/.config/gspread/authorized_user.json so subsequent runs are silent.

OAuth client credentials file path is read from OAUTH_CREDENTIALS_PATH in .env
(defaults to credentials/oauth_client.json).
"""

import os
from datetime import datetime

import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import json

import config


_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Where gspread / we cache the OAuth token after first login
_TOKEN_PATH = os.path.expanduser("~/.config/gspread/authorized_user.json")
_CLIENT_SECRETS_PATH = os.getenv("OAUTH_CREDENTIALS_PATH", "credentials.json")

# Column colour for header rows (light blue)
_HEADER_FORMAT = {
    "backgroundColor": {"red": 0.22, "green": 0.46, "blue": 0.85},
    "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
    "horizontalAlignment": "CENTER",
}


def _get_oauth_creds() -> Credentials:
    """
    Load cached OAuth token if available and still valid.
    On first run (or after expiry with no refresh token), open browser for login.
    """
    creds = None

    if os.path.exists(_TOKEN_PATH):
        with open(_TOKEN_PATH) as f:
            token_data = json.load(f)
        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes", _SCOPES),
        )

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token(creds)
        return creds

    # First-time login — opens a browser window
    if not os.path.exists(_CLIENT_SECRETS_PATH):
        raise FileNotFoundError(
            f"OAuth client secrets not found at '{_CLIENT_SECRETS_PATH}'.\n"
            "Download 'credentials/oauth_client.json' from Google Cloud Console:\n"
            "  APIs & Services → Credentials → OAuth 2.0 Client IDs → Desktop app → Download JSON\n"
            "Then re-run the tool."
        )

    flow = InstalledAppFlow.from_client_secrets_file(_CLIENT_SECRETS_PATH, _SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)
    _save_token(creds)
    return creds


def _save_token(creds: Credentials) -> None:
    os.makedirs(os.path.dirname(_TOKEN_PATH), exist_ok=True)
    with open(_TOKEN_PATH, "w") as f:
        json.dump({
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes) if creds.scopes else _SCOPES,
        }, f, indent=2)


def _connect() -> gspread.Spreadsheet:
    creds = _get_oauth_creds()
    client = gspread.authorize(creds)
    if config.GOOGLE_SHEET_ID:
        return client.open_by_key(config.GOOGLE_SHEET_ID)
    return client.open(config.GOOGLE_SHEET_NAME)


def _get_or_create_tab(spreadsheet: gspread.Spreadsheet, title: str) -> gspread.Worksheet:
    try:
        ws = spreadsheet.worksheet(title)
        ws.clear()
        return ws
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=200, cols=30)


def _format_header_row(ws: gspread.Worksheet, header_count: int) -> None:
    """Apply bold blue formatting to the first row."""
    try:
        ws.format(f"A1:{chr(64 + min(header_count, 26))}1", _HEADER_FORMAT)
    except Exception:
        pass  # Formatting is cosmetic — don't crash if it fails


def write_all(
    competitors: list,
    scraped_map: dict,
    analysis_map: dict,
    keyword_summary: list[dict],
    serp_results: dict,
    insights_text: str,
    pricing_map: dict | None = None,
    reviews_map: dict | None = None,
    gap_map: dict | None = None,
    speed_map: dict | None = None,
    social_map: dict | None = None,
) -> None:
    """
    Main entry point — writes all tabs to the Google Sheet.

    Args:
        competitors:     list[CompetitorSERP] sorted by rank
        scraped_map:     {url: ScrapedData}
        analysis_map:    {url: AnalysisResult}
        keyword_summary: output of serper_client.build_keyword_summary()
        serp_results:    {keyword: [SERPResult]} raw Serper data
        insights_text:   AI-generated overall insights string
        pricing_map:     {url: PricingData}  (optional)
        reviews_map:     {url: ReviewData}   (optional)
        gap_map:         {url: ContentGapData} (optional)
        speed_map:       {url: SpeedData}    (optional)
        social_map:      {url: SocialData}   (optional)
    """
    print("\nConnecting to Google Sheets…")
    try:
        spreadsheet = _connect()
    except Exception as e:
        print(f"  [Sheets] Connection failed: {e}")
        print("  Skipping Google Sheets write. CSV backup still saved.")
        return

    _write_analysis_tab(spreadsheet, competitors, scraped_map, analysis_map)
    _write_serp_matrix_tab(spreadsheet, competitors, serp_results)
    _write_keywords_summary_tab(spreadsheet, keyword_summary)
    # Insights Dashboard tab intentionally skipped for the FBI-apostille report (7-tab spec).

    if pricing_map:
        _write_pricing_tab(spreadsheet, competitors, pricing_map)
    if reviews_map:
        _write_reviews_tab(spreadsheet, competitors, reviews_map)
    if gap_map:
        _write_content_gaps_tab(spreadsheet, competitors, gap_map)
    if speed_map:
        _write_speed_tab(spreadsheet, competitors, speed_map)
    if social_map:
        _write_social_tab(spreadsheet, competitors, social_map)

    total_tabs = 3 + sum(bool(m) for m in [pricing_map, reviews_map, gap_map, speed_map, social_map])
    print(f"  All {total_tabs} tabs written successfully.")


# ── Tab 1: Competitor Analysis ─────────────────────────────────────────────────

def _write_analysis_tab(spreadsheet, competitors, scraped_map, analysis_map):
    ws = _get_or_create_tab(spreadsheet, config.TAB_NAMES["analysis"])

    rows = [config.ANALYSIS_HEADERS]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    for rank, comp in enumerate(competitors, 1):
        url = comp.url
        scraped = scraped_map.get(url)
        analysis = analysis_map.get(url)

        row = [
            rank,
            comp.domain,
            url,
            ", ".join(comp.keywords),
            comp.keyword_count,
            comp.best_position,
            comp.avg_position,
            # AI fields (empty string if no analysis)
            _safe(analysis, "marketing_strategy"),
            _safe(analysis, "primary_offer"),
            _safe_headlines(analysis),
            _safe(analysis, "value_proposition"),
            _safe(analysis, "pricing_transparency"),
            _safe(analysis, "social_proof"),
            _safe(analysis, "trust_signals"),
            _safe(analysis, "cold_email_signals"),
            _safe(analysis, "form_analysis"),
            # Scraper signal
            _scraper_signals(scraped),
            _safe(analysis, "workflow_logic"),
            _safe(analysis, "what_to_learn"),
            _safe(analysis, "what_to_improve"),
            _safe(analysis, "our_competitive_advantage"),
            _safe(analysis, "future_ideas"),
            now,
        ]
        rows.append(row)

    ws.update(values=rows, range_name="A1")
    _format_header_row(ws, len(config.ANALYSIS_HEADERS))

    # Freeze header row and set column widths
    ws.freeze(rows=1)
    print(f"  Tab '{config.TAB_NAMES['analysis']}' — {len(rows)-1} competitors written.")


def _safe(analysis, field: str) -> str:
    if analysis is None:
        return ""
    val = getattr(analysis, field, "")
    return str(val) if val else ""


def _safe_headlines(analysis) -> str:
    if analysis is None:
        return ""
    return analysis.headlines_str() if hasattr(analysis, "headlines_str") else ""


def _scraper_signals(scraped) -> str:
    if scraped is None:
        return ""
    parts = []
    mapping = {
        "has_blog": "Blog",
        "has_testimonials": "Testimonials",
        "has_newsletter": "Newsletter",
        "has_pricing": "Pricing",
        "has_whatsapp": "WhatsApp",
        "has_form": "Form",
        "has_live_chat": "Live Chat",
    }
    for attr, label in mapping.items():
        if getattr(scraped, attr, False):
            parts.append(label)
    return ", ".join(parts) if parts else "None detected"


# ── Tab 2: SERP Matrix ─────────────────────────────────────────────────────────

def _write_serp_matrix_tab(spreadsheet, competitors, serp_results):
    ws = _get_or_create_tab(spreadsheet, config.TAB_NAMES["matrix"])

    keywords = list(serp_results.keys())
    header = ["Domain"] + keywords
    rows = [header]

    # Build a lookup: {domain: {keyword: position}}
    from src.serper_client import _extract_domain
    position_map: dict[str, dict[str, int]] = {}
    for kw, results in serp_results.items():
        for r in results:
            domain = _extract_domain(r.link)
            if domain not in position_map:
                position_map[domain] = {}
            if kw not in position_map[domain]:  # keep best position per keyword
                position_map[domain][kw] = r.position

    for comp in competitors:
        row = [comp.domain]
        kw_positions = position_map.get(comp.domain, {})
        for kw in keywords:
            row.append(kw_positions.get(kw, ""))
        rows.append(row)

    ws.update(values=rows, range_name="A1")
    _format_header_row(ws, len(header))
    ws.freeze(rows=1, cols=1)
    print(f"  Tab '{config.TAB_NAMES['matrix']}' — {len(rows)-1} competitors × {len(keywords)} keywords.")


# ── Tab 3: Keywords Summary ────────────────────────────────────────────────────

def _write_keywords_summary_tab(spreadsheet, keyword_summary: list[dict]):
    ws = _get_or_create_tab(spreadsheet, config.TAB_NAMES["keywords"])

    headers = ["Keyword", "Total URLs Found", "Top Competitor URL", "# Unique Competitors"]
    rows = [headers]
    for item in keyword_summary:
        rows.append([
            item["keyword"],
            item["total_urls"],
            item["top_competitor"],
            item["unique_competitors"],
        ])

    ws.update(values=rows, range_name="A1")
    _format_header_row(ws, len(headers))
    ws.freeze(rows=1)
    print(f"  Tab '{config.TAB_NAMES['keywords']}' — {len(rows)-1} keywords.")


# ── Tab 4: Insights Dashboard ──────────────────────────────────────────────────

def _write_insights_tab(spreadsheet, insights_text: str):
    ws = _get_or_create_tab(spreadsheet, config.TAB_NAMES["insights"])

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = [
        ["Apostille Competitor Research — Insights Dashboard"],
        [f"Generated: {now}"],
        [""],
        [insights_text],
    ]
    ws.update(values=rows, range_name="A1")

    # Bold the title
    try:
        ws.format("A1", {"textFormat": {"bold": True, "fontSize": 14}})
    except Exception:
        pass

    print(f"  Tab '{config.TAB_NAMES['insights']}' — insights written.")


# ── Tab 5: Pricing Comparison ──────────────────────────────────────────────────

def _write_pricing_tab(spreadsheet, competitors, pricing_map: dict):
    ws = _get_or_create_tab(spreadsheet, config.TAB_NAMES["pricing"])
    headers = [
        "Domain", "Has Pricing", "Pricing Model", "Currency",
        "Transparency Score (1-5)", "Govt Fee Included", "Shipping Fee",
        "Free Services", "Package Summary", "Notes",
    ]
    rows = [headers]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for comp in competitors:
        p = pricing_map.get(comp.url)
        if not p:
            rows.append([comp.domain] + [""] * (len(headers) - 1))
            continue
        rows.append([
            comp.domain,
            "Yes" if p.has_pricing else "No",
            p.pricing_model,
            p.currency,
            p.pricing_transparency_score or "",
            "" if p.government_fee_included is None else ("Yes" if p.government_fee_included else "No"),
            p.shipping_fee,
            "; ".join(p.free_services),
            p.summary(),
            p.notes,
        ])
    ws.update(values=rows, range_name="A1")
    _format_header_row(ws, len(headers))
    ws.freeze(rows=1)
    print(f"  Tab '{config.TAB_NAMES['pricing']}' — {len(rows)-1} competitors.")


# ── Tab 6: Reviews & Trust ─────────────────────────────────────────────────────

def _write_reviews_tab(spreadsheet, competitors, reviews_map: dict):
    ws = _get_or_create_tab(spreadsheet, config.TAB_NAMES["reviews"])
    headers = [
        "Domain", "Google Rating", "Google Reviews", "Google Place Name",
        "Trustpilot Rating", "Trustpilot Reviews", "Trustpilot URL",
        "Overall Trust Score",
    ]
    rows = [headers]
    for comp in competitors:
        r = reviews_map.get(comp.url)
        if not r:
            rows.append([comp.domain] + [""] * (len(headers) - 1))
            continue
        rows.append([
            comp.domain,
            r.google_rating or "",
            r.google_review_count or "",
            r.google_place_name,
            r.trustpilot_rating or "",
            r.trustpilot_review_count or "",
            r.trustpilot_url,
            r.overall_trust_score,
        ])
    ws.update(values=rows, range_name="A1")
    _format_header_row(ws, len(headers))
    ws.freeze(rows=1)
    print(f"  Tab '{config.TAB_NAMES['reviews']}' — {len(rows)-1} competitors.")


# ── Tab 7: Content Gaps ────────────────────────────────────────────────────────

def _write_content_gaps_tab(spreadsheet, competitors, gap_map: dict):
    from src.content_gap import DOCUMENT_TYPES, USE_CASES, aggregate_gaps

    ws = _get_or_create_tab(spreadsheet, config.TAB_NAMES["content_gaps"])

    # Section 1: Per-competitor coverage summary
    headers = [
        "Domain", "Coverage Score (%)", "Content Depth", "Has Country Guides",
        "Has FAQ", "Has Process Guide", "Has State Guides", "Has Video",
        "Blog Post Count", "Top 3 Gaps",
    ]
    rows = [["=== COMPETITOR CONTENT COVERAGE ==="], headers]
    for comp in competitors:
        cg = gap_map.get(comp.url)
        if not cg:
            rows.append([comp.domain] + [""] * (len(headers) - 1))
            continue
        rows.append([
            comp.domain,
            cg.coverage_score,
            cg.content_depth,
            "Yes" if cg.has_country_guides else "No",
            "Yes" if cg.has_faq else "No",
            "Yes" if cg.has_process_explainer else "No",
            "Yes" if cg.has_state_specific_guides else "No",
            "Yes" if cg.has_video_content else "No",
            cg.blog_post_count_estimate,
            " | ".join(cg.gaps_identified[:3]),
        ])

    rows.append([""])
    rows.append(["=== TOP CROSS-SITE CONTENT GAPS (OPPORTUNITIES FOR US) ==="])
    for gap in aggregate_gaps(gap_map):
        rows.append([gap])

    ws.update(values=rows, range_name="A1")
    _format_header_row(ws, len(headers))
    ws.freeze(rows=2)
    print(f"  Tab '{config.TAB_NAMES['content_gaps']}' — {len(competitors)} competitors.")


# ── Tab 8: Page Speed ──────────────────────────────────────────────────────────

def _write_speed_tab(spreadsheet, competitors, speed_map: dict):
    ws = _get_or_create_tab(spreadsheet, config.TAB_NAMES["speed"])
    headers = [
        "Domain", "Mobile Score", "Desktop Score", "Grade",
        "FCP (ms)", "LCP (ms)", "TBT (ms)", "CLS", "TTFB (ms)",
    ]
    rows = [headers]
    for comp in competitors:
        s = speed_map.get(comp.url)
        if not s:
            rows.append([comp.domain] + [""] * (len(headers) - 1))
            continue
        rows.append([
            comp.domain,
            s.mobile_score if s.mobile_score >= 0 else "",
            s.desktop_score if s.desktop_score >= 0 else "",
            s.speed_grade,
            s.fcp_ms if s.fcp_ms >= 0 else "",
            s.lcp_ms if s.lcp_ms >= 0 else "",
            s.tbt_ms if s.tbt_ms >= 0 else "",
            s.cls_score if s.cls_score >= 0 else "",
            s.ttfb_ms if s.ttfb_ms >= 0 else "",
        ])
    ws.update(values=rows, range_name="A1")
    _format_header_row(ws, len(headers))
    ws.freeze(rows=1)
    print(f"  Tab '{config.TAB_NAMES['speed']}' — {len(rows)-1} competitors.")


# ── Tab 9: Social & Ads ────────────────────────────────────────────────────────

def _write_social_tab(spreadsheet, competitors, social_map: dict):
    ws = _get_or_create_tab(spreadsheet, config.TAB_NAMES["social"])
    headers = [
        "Domain", "Active Platforms", "Facebook", "Instagram", "LinkedIn",
        "Twitter/X", "YouTube", "FB Followers", "IG Followers", "LI Followers",
        "YT Subscribers", "Running Google Ads", "Ad Copy Samples",
    ]
    rows = [headers]
    for comp in competitors:
        s = social_map.get(comp.url)
        if not s:
            rows.append([comp.domain] + [""] * (len(headers) - 1))
            continue
        rows.append([
            comp.domain,
            ", ".join(s.active_platforms),
            s.facebook_url,
            s.instagram_url,
            s.linkedin_url,
            s.twitter_url,
            s.youtube_url,
            s.facebook_followers,
            s.instagram_followers,
            s.linkedin_followers,
            s.youtube_subscribers,
            "Yes" if s.is_running_ads else "No",
            " | ".join(s.ads_copy_samples[:2]),
        ])
    ws.update(values=rows, range_name="A1")
    _format_header_row(ws, len(headers))
    ws.freeze(rows=1)
    print(f"  Tab '{config.TAB_NAMES['social']}' — {len(rows)-1} competitors.")
