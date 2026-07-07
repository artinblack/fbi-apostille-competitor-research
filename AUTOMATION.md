# Competitor Research Automation

A multi-module Python pipeline that discovers competitors from Google search, scrapes their websites, runs AI analysis, and writes structured competitive intelligence into a **9-tab Google Sheet** (+ a local CSV backup).

This document is written so the automation can be **lifted into another project / business niche**. It is the authoritative reference — the older `README.md` is out of date (it documents only 4 tabs and an obsolete service-account auth flow). See [Porting to a new niche](#porting-to-a-new-niche).

---

## Overview

The pipeline runs in `main.py` as a sequence of steps:

```
1. SERP search   → query every keyword via Serper (Google results)
2. Dedupe        → aggregate SERP hits into unique competitor domains (cap: 50)
3. Scrape        → fetch each competitor site (Firecrawl, Jina fallback)
4. AI analysis   → structured per-competitor insights via OpenRouter
5. Insights      → AI-generated overall competitive-landscape summary
6. Extras (opt)  → pricing, reviews, content gaps, page speed, social & ads
   →→ Write CSV + Google Sheets (9 tabs) + weekly diff + optional notify
```

Steps 1–5 are the default run. Step 6 modules are opt-in via flags (or `--all-extras`).

---

## The 9 Google Sheet tabs

Tab names are defined verbatim in `config.py` → `TAB_NAMES`. Each has a dedicated `_write_*_tab()` writer in `src/sheets_client.py`.

| Tab | Contents | Produced by |
|---|---|---|
| **Competitor Analysis** | One row per competitor: rank, SERP position, AI analysis of copy / offer / value prop / forms / trust / workflow / gaps | `serper_client.py` + `analyzer.py` |
| **SERP Matrix** | Keyword × competitor position grid | `serper_client.py` |
| **Keywords Summary** | Per-keyword stats: URLs found, top competitor, unique domains | `serper_client.py` |
| **Insights Dashboard** | AI-generated overall landscape, market gaps, differentiation angles | `analyzer.py` (`generate_insights_summary`) |
| **Pricing Comparison** | AI-extracted pricing / packages per competitor | `pricing_extractor.py` (`--pricing`) |
| **Reviews & Trust** | Google Places + Trustpilot ratings, review counts | `reviews_scraper.py` (`--reviews`) |
| **Content Gaps** | Coverage/depth scoring against a target topic list; cross-competitor gaps | `content_gap.py` (`--content-gaps`) |
| **Page Speed** | Core Web Vitals from Google PageSpeed Insights | `pagespeed.py` (`--pagespeed`) |
| **Social & Ads** | Social profile detection + Google Ads Transparency activity | `social_analyzer.py` (`--social`) |

The first 4 tabs are always written; the last 5 are only written when their extra module runs.

---

## Architecture / file map

```
<repo>/
├── main.py              # Orchestrator / CLI entry point
├── config.py            # Keywords, tab names, headers, limits, env loading
├── requirements.txt     # Python deps
├── Dockerfile           # Container build
├── .env.example         # Template for all API keys / config
├── credentials.json     # Google OAuth client secrets (you provide; gitignored)
├── dashboard.py         # Streamlit viewer over the latest results CSV
├── generate_opportunities.py  # Reads the public sheet → AI → opportunities .md
├── src/
│   ├── serper_client.py     # SERP search + competitor/keyword aggregation
│   ├── scraper.py           # Firecrawl primary + Jina Reader fallback + cache
│   ├── analyzer.py          # OpenRouter per-competitor analysis + insights
│   ├── pricing_extractor.py # AI pricing extraction        → Pricing Comparison
│   ├── reviews_scraper.py   # Google Places + Trustpilot    → Reviews & Trust
│   ├── content_gap.py       # AI content-gap analysis        → Content Gaps
│   ├── pagespeed.py         # PageSpeed Insights v5          → Page Speed
│   ├── social_analyzer.py   # Social + Google Ads detection  → Social & Ads
│   ├── sheets_client.py     # OAuth2/gspread writer (all 9 tabs)
│   ├── cache.py             # Per-domain JSON cache (7-day TTL)
│   ├── scheduler.py         # Weekly diff vs previous CSV
│   ├── notifier.py          # Slack webhook + SMTP email alerts
│   ├── screenshot.py        # Playwright full-page screenshots
│   └── domain_checker.py    # Open PageRank + YouTube presence (optional)
└── output/
    ├── results_YYYY-MM-DD.csv   # CSV backup of every run
    ├── progress_YYYY-MM-DD.json # Resume state
    ├── diff_history.json        # Weekly diff log
    ├── cache/                   # Cached scraped pages
    └── screenshots/             # {domain}_YYYY-MM-DD.png
```

**Key config in `config.py`:** `MAX_COMPETITORS = 50`, `REQUEST_DELAY = 1.5`s (between scrapes), `MAX_MARKDOWN_CHARS = 6000` (page markdown sent to the AI), plus the `KEYWORDS` list and `ANALYSIS_HEADERS`.

---

## External services & API keys

Configured in `.env` (copy from `.env.example`).

| Service | Purpose | Get a key | Free tier | Required? |
|---|---|---|---|---|
| **Serper** | Google SERP results | https://serper.dev | 2,500 queries | **Required** |
| **OpenRouter** | AI analysis (default `anthropic/claude-sonnet-4-5`) | https://openrouter.ai | pay-as-you-go | **Required** |
| **Firecrawl** | Website scraping | https://firecrawl.dev | 1,000 credits/mo | Recommended (Jina fallback if absent) |
| **Google Sheets/Drive** | Write the 9 tabs | Google Cloud Console (OAuth) | free | Required to write to Sheets |
| **Google PageSpeed** | Core Web Vitals | no key needed for basic use | — | Optional (`--pagespeed`) |
| **Open PageRank** | Domain authority | https://openpagerank.com | free | Optional |
| **Slack / SMTP** | Completion alerts | Slack webhook / Gmail App Password | free | Optional (`--notify`) |

Env vars: `SERPER_API_KEY`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `FIRECRAWL_API_KEY`, `GOOGLE_SHEET_NAME`, `OAUTH_CREDENTIALS_PATH`, `OPEN_PAGERANK_API_KEY`, `SLACK_WEBHOOK_URL`, `SMTP_HOST/PORT/USER/PASS`, `ALERT_EMAIL`.

---

## Setup

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium        # only needed for screenshots
```

Requires **Python 3.10+**.

### 2. Configure API keys

```bash
cp .env.example .env
```

Fill in at minimum `SERPER_API_KEY` and `OPENROUTER_API_KEY`. `FIRECRAWL_API_KEY` is strongly recommended (without it, the free Jina fallback is used for every site — slower and weaker on JS-heavy pages).

### 3. Google Sheets — OAuth setup (one-time browser login)

> **Note:** This uses an **OAuth Desktop-app** flow via `gspread`, **not** a service account. (The old `README.md` says service account — ignore it.)

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create/select a project.
2. Enable both **Google Sheets API** and **Google Drive API**.
3. **APIs & Services → Credentials → Create credentials → OAuth 2.0 Client ID**.
4. Application type: **Desktop app** → Create → **Download JSON**.
5. Save that file as `credentials.json` in the repo root (or set `OAUTH_CREDENTIALS_PATH` to its location).
6. **APIs & Services → OAuth consent screen** → User type **External** → add your Google account as a **test user**.
7. Create a Google Sheet whose name exactly matches `GOOGLE_SHEET_NAME` in `.env`.

**First run:** a browser window opens for you to log in and grant access. The token is then cached at `~/.config/gspread/authorized_user.json` and reused on every subsequent run.

---

## Running it

```bash
python main.py                  # Full default run (SERP → dedupe → scrape → AI → insights)
```

| Flag | Effect / when to use |
|---|---|
| `--limit N` | Process only the first N competitors — use `--limit 5` to smoke-test keys cheaply |
| `--keywords-only` | SERP search only; no scrape, no AI — just see who ranks |
| `--skip-ai` | Scrape but skip OpenRouter — saves credits |
| `--resume` | Skip URLs already recorded in today's progress file (recover an interrupted run) |
| `--dry-run` | Run everything but skip CSV/Sheets writes — safe for testing |
| `--no-screenshots` | Skip Playwright capture |
| `--pagespeed` | Add the Page Speed tab |
| `--reviews` | Add the Reviews & Trust tab |
| `--pricing` | Add the Pricing Comparison tab |
| `--content-gaps` | Add the Content Gaps tab |
| `--social` | Add the Social & Ads tab |
| `--all-extras` | Enable all five extra modules at once |
| `--notify` | Send Slack/email on completion |

Typical full intelligence run:

```bash
python main.py --all-extras --notify
```

CSV backup is always written to `output/results_YYYY-MM-DD.csv` regardless of Sheets access.

---

## Cost estimate (one full run, 50 competitors)

| Service | Usage | Approx cost |
|---|---|---|
| Serper | ~22 searches | Free (within 2,500 free queries) |
| Firecrawl | ~50 scrapes | Free (within 1,000 free credits/mo) |
| OpenRouter — Sonnet | 50 analyses + 1 summary | ~$2–5 |
| OpenRouter — Haiku | 50 analyses + 1 summary | ~$0.30 |

Set `OPENROUTER_MODEL=anthropic/claude-haiku-4-5` for a ~10× cheaper run at lower analysis depth.

---

## Porting to a new niche

The pipeline is **niche-agnostic infrastructure with a thin niche-specific layer on top**. To retarget it at a different business/vertical, copy the files below and edit only the handful of touchpoints in the table.

### Copy these into the new project

```
main.py  config.py  requirements.txt  .env.example  Dockerfile  src/
```

Optionally also `dashboard.py` and `generate_opportunities.py`. Do **not** copy `credentials.json`, `.env`, or `output/` — those are per-deployment.

### What to change

| File | Where | Change |
|---|---|---|
| `config.py` | `KEYWORDS = [...]` | Replace with the target niche's search keywords |
| `config.py` | `GOOGLE_SHEET_NAME` (or set in `.env`) | Point at the new Sheet's exact name |
| `config.py` | `MAX_COMPETITORS`, `ANALYSIS_HEADERS` | Adjust cap / columns if desired (optional) |
| `src/serper_client.py` | `gl="in"`, `hl="en"` (~L77) | Set the target country/language locale |
| `src/serper_client.py` | junk-domain blocklist (~L61) | Swap the region marketplaces (e.g. `justdial.com`, `sulekha.com`) for ones relevant to the new market |
| `src/analyzer.py` | system prompt (~L35–37) | Rewrite the "who we are / what we sell" framing (currently apostille agency in India) |
| `src/content_gap.py` | `DOCUMENT_TYPES` (~L18) + prompt (~L48) | Replace the topic list and analyst framing for the new domain |
| `src/analyzer.py`, `src/content_gap.py` | `HTTP-Referer` / `X-Title` headers | Rename from `apostille-research-tool` (cosmetic, for OpenRouter attribution) |

### Leave as-is (generic)

`main.py` (orchestration), `scraper.py`, `sheets_client.py`, `pricing_extractor.py`, `reviews_scraper.py`, `pagespeed.py`, `social_analyzer.py`, `cache.py`, `scheduler.py`, `notifier.py`, `screenshot.py`, `domain_checker.py`. These contain no niche assumptions.

### New-project checklist

1. Copy files above; `pip install -r requirements.txt`.
2. Edit the touchpoints in the table.
3. Create a **new** Google Sheet and set `GOOGLE_SHEET_NAME`.
4. Create **new** OAuth credentials for the new project (or reuse existing `credentials.json` if the same Google account is fine).
5. `cp .env.example .env`, fill keys.
6. Smoke-test: `python main.py --limit 5`.
7. Full run: `python main.py --all-extras`.

---

## Outputs

- `output/results_YYYY-MM-DD.csv` — full CSV backup (every competitor, all columns).
- `output/progress_YYYY-MM-DD.json` — per-URL progress for `--resume`.
- `output/diff_history.json` — weekly diff vs the previous run (via `scheduler.py`).
- `output/cache/` — cached scraped pages (7-day TTL, `cache.py`).
- `output/screenshots/` — `{domain}_YYYY-MM-DD.png` homepage captures.
- **`dashboard.py`** — `streamlit run dashboard.py` opens an interactive viewer over the latest results CSV.
- **`generate_opportunities.py`** — pulls all tabs from the public Google Sheet and asks Claude (via OpenRouter) to produce a page/feature-opportunities markdown report. Note it hard-codes a `SHEET_ID`; update that when porting.

---

## Troubleshooting

**`SERPER_API_KEY not set`** — `.env` missing or key blank.

**`gspread.exceptions.SpreadsheetNotFound`** — `GOOGLE_SHEET_NAME` must match the sheet's name exactly (case-sensitive), and the sheet must be owned by / accessible to the Google account you authorized in the OAuth flow.

**OAuth browser prompt every run** — the cached token at `~/.config/gspread/authorized_user.json` isn't being written; check filesystem permissions. Delete that file to force a clean re-auth.

**Firecrawl credits exhausted** — the Jina Reader fallback kicks in automatically. It works on static sites; JS-heavy pages may return incomplete content.

**OpenRouter 401 Unauthorized** — check `OPENROUTER_API_KEY` and that the account has credits.

**Malformed-JSON AI response** — the model returned invalid JSON; the raw response is saved in the `AI Error` CSV column. Try a different `OPENROUTER_MODEL`.
