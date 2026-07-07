"""
Dedicated AI-powered pricing extractor.
Sends page markdown to OpenRouter with a pricing-specific prompt and
returns structured pricing data per competitor.
Produces a comparison table: [Service] × [Competitor].
"""

import json
import re
from dataclasses import dataclass, field

import requests

import config


OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM_PROMPT = """\
You are a pricing intelligence analyst. Extract all pricing information from this competitor website
for a US apostille document fulfillment service. Return ONLY a JSON object (no markdown) with:

{
  "has_pricing": true | false,
  "pricing_model": "flat_rate" | "tiered" | "custom_quote" | "not_disclosed",
  "currency": "USD" | "INR" | "mixed" | "unknown",
  "packages": [
    {
      "name": "Package or service name",
      "price": "Price as string (e.g. '$120' or '₹5,000')",
      "includes": "What this package includes",
      "turnaround": "Processing time if mentioned"
    }
  ],
  "document_prices": {
    "fbi_background_check": "price or empty string",
    "birth_certificate": "price or empty string",
    "degree_certificate": "price or empty string",
    "marriage_certificate": "price or empty string",
    "divorce_decree": "price or empty string",
    "other": "any other pricing mentioned"
  },
  "government_fee_included": true | false | null,
  "shipping_fee": "shipping cost or 'included' or 'not mentioned'",
  "free_services": ["list of anything offered free, e.g. 'free document review', 'free pickup'"],
  "pricing_transparency_score": 1-5,
  "notes": "Any important pricing notes, discounts, or conditions"
}

If no pricing information is visible, set has_pricing to false and return empty/null values."""


@dataclass
class PricingData:
    url: str
    has_pricing: bool = False
    pricing_model: str = ""
    currency: str = ""
    packages: list = field(default_factory=list)
    document_prices: dict = field(default_factory=dict)
    government_fee_included: bool | None = None
    shipping_fee: str = ""
    free_services: list = field(default_factory=list)
    pricing_transparency_score: int = 0
    notes: str = ""
    error: str = ""

    def summary(self) -> str:
        if not self.has_pricing:
            return "No pricing disclosed"
        pkgs = "; ".join(
            f"{p.get('name','?')}={p.get('price','?')}" for p in self.packages[:3]
        )
        return pkgs or self.pricing_model or "Pricing detected but unstructured"


def extract(url: str, scraped) -> PricingData:
    """Extract pricing from already-scraped page content."""
    if not config.OPENROUTER_API_KEY:
        return PricingData(url=url, error="OPENROUTER_API_KEY not set")

    markdown = getattr(scraped, "markdown", "") or ""
    if not markdown:
        return PricingData(url=url, error="No page content")

    # Focus on the most pricing-relevant sections
    excerpt = markdown[:8000]

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://apostille-research-tool",
    }
    payload = {
        "model": config.OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"URL: {url}\n\nPage content:\n{excerpt}"},
        ],
        "temperature": 0.1,
        "max_tokens": 800,
    }

    try:
        resp = requests.post(OPENROUTER_ENDPOINT, json=payload, headers=headers, timeout=45)
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return PricingData(url=url, error=str(e))

    # Parse JSON response
    text = raw.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                return PricingData(url=url, error="Could not parse pricing JSON")
        else:
            return PricingData(url=url, error="No JSON in response")

    return PricingData(
        url=url,
        has_pricing=parsed.get("has_pricing", False),
        pricing_model=parsed.get("pricing_model", ""),
        currency=parsed.get("currency", ""),
        packages=parsed.get("packages", []),
        document_prices=parsed.get("document_prices", {}),
        government_fee_included=parsed.get("government_fee_included"),
        shipping_fee=parsed.get("shipping_fee", ""),
        free_services=parsed.get("free_services", []),
        pricing_transparency_score=int(parsed.get("pricing_transparency_score", 0)),
        notes=parsed.get("notes", ""),
    )


def extract_all(competitors: list, scraped_map: dict) -> dict[str, PricingData]:
    """Extract pricing for all competitors."""
    results: dict[str, PricingData] = {}
    total = len(competitors)
    for i, comp in enumerate(competitors, 1):
        scraped = scraped_map.get(comp.url)
        print(f"  [{i}/{total}] Pricing: {comp.domain}")
        results[comp.url] = extract(comp.url, scraped)
        p = results[comp.url]
        print(f"    ✓ {p.summary()}" if not p.error else f"    ✗ {p.error}")
    return results


def build_comparison_table(competitors: list, pricing_map: dict) -> list[list]:
    """
    Build a [Service] × [Competitor] comparison grid for the Google Sheet.
    Rows = document types, Columns = competitor domains.
    """
    doc_types = [
        "fbi_background_check", "birth_certificate", "degree_certificate",
        "marriage_certificate", "divorce_decree", "other",
    ]
    domains = [c.domain for c in competitors]

    header = ["Document Type"] + domains
    rows = [header]

    for doc in doc_types:
        row = [doc.replace("_", " ").title()]
        for comp in competitors:
            pd = pricing_map.get(comp.url)
            if pd and pd.document_prices:
                row.append(pd.document_prices.get(doc, ""))
            else:
                row.append("")
        rows.append(row)

    # Package summary row
    pkg_row = ["Package Summary"]
    for comp in competitors:
        pd = pricing_map.get(comp.url)
        pkg_row.append(pd.summary() if pd else "")
    rows.append(pkg_row)

    return rows
