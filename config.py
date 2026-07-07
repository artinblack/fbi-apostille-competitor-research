import os
from dotenv import load_dotenv

load_dotenv()

# ── API credentials ────────────────────────────────────────────────────────────
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4-5")
RESEARCH_MODEL = os.getenv("RESEARCH_MODEL", "perplexity/sonar-pro")  # Stage-1 web research model
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "FBI Apostille Competitor Research")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")  # if set, opened by key (preferred over name)
OAUTH_CREDENTIALS_PATH = os.getenv("OAUTH_CREDENTIALS_PATH", "credentials.json")
OPEN_PAGERANK_API_KEY = os.getenv("OPEN_PAGERANK_API_KEY", "")  # optional: openpagerank.com free key
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "")

# ── Scraping settings ──────────────────────────────────────────────────────────
REQUEST_DELAY = 1.5       # seconds between Firecrawl calls
MAX_COMPETITORS = 60      # cap on unique competitor domains to process
MAX_MARKDOWN_CHARS = 6000 # chars of page markdown sent to the AI

# ── Google Sheets tab names ────────────────────────────────────────────────────
TAB_NAMES = {
    "analysis":      "Competitor Analysis",
    "matrix":        "SERP Matrix",
    "keywords":      "Keywords Summary",
    "insights":      "Insights Dashboard",
    "pricing":       "Pricing Comparison",
    "reviews":       "Reviews & Trust",
    "content_gaps":  "Content Gaps",
    "speed":         "Page Speed",
    "social":        "Social & Ads",
}

# ── Column headers for Tab 1 ───────────────────────────────────────────────────
ANALYSIS_HEADERS = [
    "Overall Rank",
    "Domain",
    "URL",
    "Keywords Found In",
    "# Keywords Ranking",
    "Best SERP Position",
    "Avg SERP Position",
    "Marketing Strategy",
    "Primary Offer",
    "Key Headlines & Copy",
    "Value Proposition",
    "Pricing Transparency",
    "Social Proof",
    "Trust Signals",
    "Cold Email Signals",
    "Form Analysis",
    "Content Marketing",
    "Workflow Logic",
    "What to Learn",
    "What They Can Improve",
    "Our Competitive Advantage",
    "Future Ideas",
    "Last Analyzed",
]

# ── Deep-research allowlist ─────────────────────────────────────────────────────
# Only these competitor domains get metered AI content (Sonar research + synthesis).
# All other competitors still get SERP + reviews + social (no AI spend).
AI_ANALYSIS_DOMAINS = [
    "monumentvisa.com",
    "fbiapostilleservices.com",
    "dcmobilenotary.com",
    "visadc.com",
    "rocadc.com",
    "globeia.com",
    "federalapostille.org",
]

# ── Keywords ───────────────────────────────────────────────────────────────────
# FBI apostille niche (US-based FBI background-check apostille services)
KEYWORDS = [
    "fbi apostille",
    "fbi apostille services",
    "fbi apostille background check",
    "fbi apostille service",
    "fbi apostille washington dc",
    "fbi apostille services washington dc",
    "fbi apostille services spain",
    "fbi apostille spain",
    "fbi apostille services reviews",
    "fbi apostille services colombia",
    "fbi apostille services arizona",
    "fbi apostille services california",
    "fbi apostille expedite",
    "fbi apostille services minnesota",
    "fbi apostille services washington",
    "fbi apostille processing time",
    "fbi apostille legalization washington dc",
    "fbi apostille services oklahoma",
    "fbi apostille services oregon",
    "fbi apostille services texas",
]
