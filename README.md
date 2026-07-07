# FBI Apostille — Competitor Research Automation

A Python pipeline that discovers competitors from Google search for **FBI background-check
apostille** keywords, scrapes their sites, runs AI competitive analysis, and writes structured
intelligence into a multi-tab Google Sheet (+ a local CSV backup).

It supports two analysis depths:

- **Standard** — one page per competitor → OpenRouter model → JSON.
- **Deep** (`deep_research.py`) — multi-page scrape **+ live web research** via Perplexity Sonar
  (`perplexity/sonar-pro`) over OpenRouter, then hand/AI synthesis written to the sheet via
  `main.py --ai-from-json`.

> See [AUTOMATION.md](AUTOMATION.md) for the full architecture reference and
> [FUTURE_FEATURES.md](FUTURE_FEATURES.md) for the enhancement backlog.

## Google Sheet tabs

`Competitor Analysis` · `SERP Matrix` · `Keywords Summary` · `Pricing Comparison` ·
`Reviews & Trust` · `Content Gaps` · `Social & Ads`

## Setup

```bash
python3 -m pip install -r requirements.txt      # requests, firecrawl-py, gspread, google-auth*, python-dotenv, streamlit, pandas
cp .env.example .env                            # then fill in your keys
```

Required keys in `.env`: `SERPER_API_KEY`, `FIRECRAWL_API_KEY`, `OPENROUTER_API_KEY`.
Google Sheets uses an OAuth **Desktop-app** `credentials.json` (see AUTOMATION.md → Google Sheets setup).
Set `GOOGLE_SHEET_ID` (preferred) or `GOOGLE_SHEET_NAME`.

## Usage

```bash
# Standard run — all non-AI tabs (SERP, reviews, social), no OpenRouter spend
python3 main.py --skip-ai --reviews --social --no-screenshots

# Deep research for the allowlisted competitors (config.AI_ANALYSIS_DOMAINS)
python3 deep_research.py                                   # Stage 1: Sonar research + multi-page scrape (metered)
# → synthesize output/ai_synthesis.json, then:
python3 main.py --ai-from-json output/ai_synthesis.json --reviews --social --no-screenshots

# Interactive dashboard over the latest results CSV
python3 -m streamlit run dashboard.py
```

Key config lives in [config.py](config.py): `KEYWORDS`, `AI_ANALYSIS_DOMAINS`, `RESEARCH_MODEL`,
`MAX_COMPETITORS`, `ANALYSIS_HEADERS`.

## Layout

```
main.py              # Orchestrator / CLI (incl. --ai-from-json)
deep_research.py     # Stage-1 deep research runner (metered)
config.py            # Keywords, allowlist, models, tab names, headers
dashboard.py         # Streamlit viewer over the latest CSV
src/
  serper_client.py   # SERP search + competitor/keyword aggregation
  scraper.py         # Firecrawl primary + Jina fallback + cache
  researcher.py      # Multi-page scrape + Perplexity Sonar research (deep mode)
  analyzer.py        # OpenRouter per-competitor analysis
  pricing_extractor.py / reviews_scraper.py / content_gap.py / social_analyzer.py / pagespeed.py
  sheets_client.py   # OAuth2 gspread writer (all tabs)
  cache.py / scheduler.py / notifier.py / screenshot.py / domain_checker.py
```

## Notes

- Secrets (`.env`, `credentials.json`) and generated `output/` are gitignored.
- OpenRouter cost is controlled by `AI_ANALYSIS_DOMAINS` — AI runs only for listed competitors.
