"""
AI-powered competitor analysis via OpenRouter.
Sends scraped markdown to the configured model and returns a structured
AnalysisResult with all insight fields.
"""

import json
import re
import time
from dataclasses import dataclass

import requests

import config

_MAX_RETRIES = 3


def _retry_request(fn, max_retries: int = _MAX_RETRIES):
    """Call fn() with exponential backoff. Re-raises final exception."""
    last_exc = None
    for attempt in range(max_retries):
        try:
            return fn()
        except requests.RequestException as e:
            last_exc = e
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    raise last_exc


OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM_PROMPT = """\
You are a competitive intelligence analyst for a US-based FBI background-check apostille service.
The service helps clients get their FBI Identity History Summary (background check / PCC) — and other
US documents — authenticated/apostilled by the US Department of State so they can be used abroad
(for residency, work, and visas in countries such as Spain, Colombia, Italy, UAE, and Mexico). Clients
are typically US residents, immigrants, and expats who need fast, reliable federal-document apostilles.

Your job: analyze a competitor website and return a JSON object (no markdown, no extra text —
raw JSON only) with exactly these fields:

{
  "marketing_strategy": "How they attract clients: SEO, paid ads, social media, referrals, content, etc.",
  "primary_offer": "What exactly they are selling — the main service/package.",
  "key_headlines": ["Top H1/H2 verbatim quote 1", "Quote 2", "Quote 3"],
  "value_proposition": "The core unique selling point or promise they make to customers.",
  "pricing_transparency": "Yes | No | Partial",
  "social_proof": "Describe testimonials, star ratings, review counts, case studies, logos of clients.",
  "trust_signals": "Certifications, years in business, affiliations, government tie-ups, media mentions.",
  "cold_email_signals": "Newsletter signup, lead magnets, free guides, chat/SMS opt-in, anything suggesting email/SMS outreach strategy.",
  "form_analysis": "Describe the contact or order form: fields present, CTA button copy, ease of use, what friction exists.",
  "content_marketing": "Blog posts, FAQs, guides, videos — what educational content do they publish and how much?",
  "workflow_logic": "Based on the site, how do they appear to handle orders? What steps does a customer take?",
  "what_to_learn": "The single most valuable thing to copy or learn from this competitor.",
  "what_to_improve": "The biggest weakness or gap in their offering that we could exploit.",
  "our_competitive_advantage": "Specific ways our FBI apostille service could beat or differentiate from this competitor.",
  "future_ideas": "Creative ideas inspired by this competitor that we could implement in our own business."
}

Be specific and actionable. Reference actual content from the page where possible.
If you cannot determine something from the available content, write "Not determinable from available content."
"""


@dataclass
class AnalysisResult:
    marketing_strategy: str = ""
    primary_offer: str = ""
    key_headlines: list[str] = None
    value_proposition: str = ""
    pricing_transparency: str = ""
    social_proof: str = ""
    trust_signals: str = ""
    cold_email_signals: str = ""
    form_analysis: str = ""
    content_marketing: str = ""
    workflow_logic: str = ""
    what_to_learn: str = ""
    what_to_improve: str = ""
    our_competitive_advantage: str = ""
    future_ideas: str = ""
    raw_response: str = ""
    error: str = ""

    def __post_init__(self):
        if self.key_headlines is None:
            self.key_headlines = []

    def headlines_str(self) -> str:
        return " | ".join(self.key_headlines) if self.key_headlines else ""


def _build_user_prompt(url: str, scraped) -> str:
    markdown_excerpt = scraped.markdown[:config.MAX_MARKDOWN_CHARS]

    signals = []
    if scraped.has_testimonials:
        signals.append("testimonials/reviews detected")
    if scraped.has_newsletter:
        signals.append("newsletter/subscription detected")
    if scraped.has_blog:
        signals.append("blog/articles detected")
    if scraped.has_pricing:
        signals.append("pricing information detected")
    if scraped.has_whatsapp:
        signals.append("WhatsApp contact detected")
    if scraped.has_form:
        signals.append("contact/inquiry form detected")
    if scraped.has_live_chat:
        signals.append("live chat detected")

    signal_str = ", ".join(signals) if signals else "none detected"

    return f"""Competitor URL: {url}
Page Title: {scraped.title or 'Not found'}
Meta Description: {scraped.meta_description or 'Not found'}
Quick Signals: {signal_str}
Scrape Method: {scraped.scrape_method}

--- PAGE CONTENT (markdown) ---
{markdown_excerpt}
--- END OF CONTENT ---

Return the JSON analysis object now."""


def _parse_json_response(text: str) -> dict:
    """Extract JSON from the model response even if it has surrounding text."""
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON block from markdown fences
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find the outermost {...}
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from response:\n{text[:500]}")


def analyze(url: str, scraped, serp_data=None) -> AnalysisResult:
    """
    Send scraped competitor data to OpenRouter and return an AnalysisResult.
    Returns an AnalysisResult with error set if the call fails.
    """
    if not config.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not set in .env")

    if scraped.scrape_method == "failed" or not scraped.markdown:
        return AnalysisResult(error="No page content to analyze — scrape failed.")

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://apostille-research-tool",
        "X-Title": "Apostille Competitor Research",
    }

    payload = {
        "model": config.OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": _build_user_prompt(url, scraped)},
        ],
        "temperature": 0.3,
        "max_tokens": 2000,
    }

    try:
        resp = _retry_request(
            lambda: requests.post(OPENROUTER_ENDPOINT, json=payload, headers=headers, timeout=60)
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        return AnalysisResult(error=f"OpenRouter request failed: {e}")

    raw = resp.json()
    raw_text = raw.get("choices", [{}])[0].get("message", {}).get("content", "")

    try:
        parsed = _parse_json_response(raw_text)
    except ValueError as e:
        return AnalysisResult(raw_response=raw_text, error=str(e))

    headlines = parsed.get("key_headlines", [])
    if isinstance(headlines, str):
        headlines = [headlines]

    return AnalysisResult(
        marketing_strategy=parsed.get("marketing_strategy", ""),
        primary_offer=parsed.get("primary_offer", ""),
        key_headlines=headlines,
        value_proposition=parsed.get("value_proposition", ""),
        pricing_transparency=parsed.get("pricing_transparency", ""),
        social_proof=parsed.get("social_proof", ""),
        trust_signals=parsed.get("trust_signals", ""),
        cold_email_signals=parsed.get("cold_email_signals", ""),
        form_analysis=parsed.get("form_analysis", ""),
        content_marketing=parsed.get("content_marketing", ""),
        workflow_logic=parsed.get("workflow_logic", ""),
        what_to_learn=parsed.get("what_to_learn", ""),
        what_to_improve=parsed.get("what_to_improve", ""),
        our_competitive_advantage=parsed.get("our_competitive_advantage", ""),
        future_ideas=parsed.get("future_ideas", ""),
        raw_response=raw_text,
    )


def generate_insights_summary(all_analyses: list[tuple[str, AnalysisResult]]) -> str:
    """
    Call the AI once more with a summary of all competitors to produce the
    Insights Dashboard text (overall landscape, gaps, opportunities).
    """
    if not config.OPENROUTER_API_KEY:
        return "OPENROUTER_API_KEY not set — skipped."

    summaries = []
    for url, ar in all_analyses:
        if ar.error:
            continue
        summaries.append(
            f"- {url}: offer='{ar.primary_offer}' | USP='{ar.value_proposition}' | "
            f"weakness='{ar.what_to_improve}'"
        )

    if not summaries:
        return "No valid analyses to summarize."

    prompt = f"""You are a competitive intelligence strategist for a US-based FBI background-check
apostille service. Below are summaries of {len(summaries)} competitors found in Google US
search results for FBI-apostille-related keywords.

Competitors:
{chr(10).join(summaries)}

Write a strategic Insights Dashboard (plain text, not JSON) covering:
1. Overall competitive landscape (2-3 sentences)
2. Common patterns across top competitors (bullet points)
3. Top 3 market gaps / underserved needs you identified
4. Our top 3 differentiation angles to exploit
5. 3 creative future ideas inspired by the competitive landscape

Be specific, actionable, and focused on the US FBI-background-check apostille market."""

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://apostille-research-tool",
    }
    payload = {
        "model": config.OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "max_tokens": 1500,
    }

    try:
        resp = requests.post(OPENROUTER_ENDPOINT, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Insights generation failed: {e}"
