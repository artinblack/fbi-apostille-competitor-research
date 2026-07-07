# FBI Apostille Competitor Automation — Future Features

Enhancement backlog for the competitor-research pipeline (`main.py` + `src/`) and the
Google Sheet it writes. Ordered by priority tier. Each item notes the **effort**, the
**module** it touches, and the **sheet impact**.

Context: the current run is **AI-disabled** (no OpenRouter key) and produces 5 live tabs
— Competitor Analysis (SERP only), SERP Matrix, Keywords Summary, Reviews & Trust,
Social & Ads. The biggest wins below re-activate the dormant AI value and harden the
data quality issues seen in the first runs.

---

## Tier 1 — High value, low effort

### 1. Re-enable the AI analysis tabs
- **Why:** The whole "intelligence" layer (marketing strategy, value prop, pricing
  extraction, content-gap opportunities) is currently blank — it needs an OpenRouter key.
- **How:** Add `OPENROUTER_API_KEY` to `.env`, then run with
  `--pricing --content-gaps` and drop `--skip-ai`. Fills the AI columns of
  **Competitor Analysis** plus the **Pricing Comparison** and **Content Gaps** tabs.
- **Module:** `analyzer.py`, `pricing_extractor.py`, `content_gap.py` (already wired).
- **Effort:** Trivial (config only).

### 2. Reviews accuracy — match on website, not fuzzy name
- **Why:** The Google Places lookup does a loose text search (`"{domain} apostille"`), so
  a few rows attach the wrong business (e.g. a competitor's row showing another firm's
  rating). Fixed the country bias (`gl=us`); matching precision is the next gap.
- **How:** After the Places search, verify the returned place's `website`/domain matches
  the competitor domain; if not, blank the rating and add a **"Match Confidence"** column
  (High/Low). Optionally fall back to a homepage JSON-LD `aggregateRating` scrape.
- **Module:** `reviews_scraper.py`, `sheets_client._write_reviews_tab`.
- **Effort:** Low.

### 3. Contact & lead extraction (for outreach)
- **Why:** Enables the "cold email / partnership" workflow the analyzer already hints at.
- **How:** Regex + scrape emails, phone numbers, and contact-page URLs from the already
  cached markdown. New **Contacts** tab: Domain, Email(s), Phone, Contact URL, WhatsApp.
- **Module:** new `contact_extractor.py`, reuse `scraper.py` cache.
- **Effort:** Low.

---

## Tier 2 — High value, medium effort

### 4. Keyword auto-expansion
- **Why:** Currently a fixed list of 20. Serper returns "People Also Ask" and "related
  searches" that surface new long-tail keywords (states, destination countries, use cases).
- **How:** Parse `peopleAlsoAsk` + `relatedSearches` from each SERP response, dedupe
  against `KEYWORDS`, and write a **Keyword Opportunities** tab (suggested keyword,
  source, seed keyword). Optionally auto-append high-value ones next run.
- **Module:** `serper_client.py`.
- **Effort:** Medium.

### 5. SERP feature tracking
- **Why:** Ranking position alone misses who owns featured snippets, the local pack, PAA,
  and site links — the real visibility on FBI-apostille queries.
- **How:** Capture `answerBox`, `peopleAlsoAsk`, `places` (local pack), sitelinks per
  keyword. Add columns to **SERP Matrix** or a new **SERP Features** tab.
- **Module:** `serper_client.py`, `sheets_client.py`.
- **Effort:** Medium.

### 6. Real ad intelligence (Google + Meta)
- **Why:** This run detected **0 competitors running ads**, which is almost certainly a
  detector gap, not reality — paid competition on these keywords is high.
- **How:** Query the Google Ads Transparency Center and Meta Ad Library per domain; pull
  active-ad counts, creative text, and first-seen dates into **Social & Ads**.
- **Module:** `social_analyzer.py`.
- **Effort:** Medium (needs the transparency endpoints / light scraping).

### 7. Destination-country SERPs (Spain, Colombia, etc.)
- **Why:** Several keywords target `spain` / `colombia`; those users often search on
  `google.es` / `google.com.co`. US-only SERP misses local competitors.
- **How:** Add a `LOCALES` config (e.g. `us`, `es`, `co`) and run key keywords per locale;
  tag each SERP row with its locale.
- **Module:** `serper_client.py`, `config.py`.
- **Effort:** Medium.

---

## Tier 3 — Strategic / longer effort

### 8. Historical tracking & rank-movement dashboard
- **Why:** A single snapshot can't show who's rising or falling. `scheduler.py` already
  writes a weekly diff — surface it visually.
- **How:** Append each run's positions to a history store; add a **Trends** tab with
  first-seen / last-seen / position delta per domain. Pair with the scheduled cron run.
- **Module:** `scheduler.py`, new history writer.
- **Effort:** Medium–High.

### 9. Scheduled autonomous runs + digest
- **Why:** Keep the sheet fresh without manual runs.
- **How:** Cron (weekly) → full run → Slack/email digest of new competitors and rank
  changes. `notifier.py` and `--notify` are already built; add a scheduler entry.
- **Module:** `notifier.py`, cron/CI.
- **Effort:** Low–Medium (infra).

### 10. Business-entity de-duplication
- **Why:** Some competitors operate multiple domains (state-specific microsites) that are
  the same company — inflating the count and skewing coverage.
- **How:** Cluster by shared phone/address/brand from the contact extractor; add a
  **"Parent Entity"** column to Competitor Analysis.
- **Module:** new clustering step post-`contact_extractor`.
- **Effort:** High.

### 11. Review sentiment & theme mining
- **Why:** Ratings tell "how good"; review text tells "why" — turnaround time, price,
  communication — the real differentiation levers.
- **How:** Pull recent review snippets (Serper Places / scrape) and AI-summarise top
  praises & complaints per competitor into **Reviews & Trust**.
- **Module:** `reviews_scraper.py` + `analyzer.py`.
- **Effort:** High (needs AI).

### 12. Content-gap → auto content brief
- **Why:** Turn the Content Gaps tab from a diagnosis into an action.
- **How:** For each top cross-site gap, have the AI draft a page brief (title, H2s, target
  keyword, word count) into a **Content Briefs** tab.
- **Module:** `content_gap.py` + `analyzer.py`.
- **Effort:** Medium (needs AI).

### 13. Re-add Page Speed & Insights tabs (optional)
- **Why:** Dropped for the 7-tab spec, but Core Web Vitals and an AI landscape summary
  are cheap signal.
- **How:** Run with `--pagespeed`; un-skip `_write_insights_tab` in `sheets_client.py`.
- **Module:** `pagespeed.py`, `sheets_client.py` (already built).
- **Effort:** Trivial.

---

## Quick-win checklist (next session)

1. Add `OPENROUTER_API_KEY`, run `python main.py --reviews --social --pricing --content-gaps`
   → unlocks 2 more tabs + all AI columns.
2. Add the reviews **Match Confidence** column (#2).
3. Add the **Contacts** tab (#3).
4. Turn on keyword auto-expansion (#4) to grow the keyword set automatically.
