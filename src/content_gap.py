"""
FBI Apostille Content Gap Analyzer.
Maps which document types each competitor covers in their content,
identifies uncovered niches, and generates SEO opportunity recommendations.
"""

import json
import re
from dataclasses import dataclass, field

import requests

import config


OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

# Document types we care about (US federal/state documents apostilled for use abroad)
DOCUMENT_TYPES = [
    "FBI Background Check (Identity History Summary)",
    "Channeler / Livescan Fingerprinting",
    "Notarized Documents",
    "State-issued Documents",
    "Birth Certificate",
    "Marriage Certificate",
    "Divorce Decree",
    "Degree / Diploma / Transcript",
    "Death Certificate",
    "Power of Attorney",
    "Court Documents",
    "Company / Business Documents",
]

# Use cases (destination countries / purposes for an FBI apostille)
USE_CASES = [
    "Spain (residency/work)",
    "Colombia",
    "Italy",
    "Mexico",
    "UAE / Gulf Employment",
    "Germany / Europe Visa",
    "Student / Work Visa Abroad",
    "Immigration / Residency",
    "Dual Citizenship",
]

_SYSTEM_PROMPT = f"""\
You are a content gap analyst for a US-based FBI background-check apostille service.
Analyze this competitor website and return ONLY a JSON object (no markdown) with:

{{
  "document_coverage": {{
    {', '.join(f'"{d}": true | false' for d in DOCUMENT_TYPES)}
  }},
  "use_case_coverage": {{
    {', '.join(f'"{u}": true | false' for u in USE_CASES)}
  }},
  "content_depth": "shallow" | "moderate" | "deep",
  "has_destination_country_guides": true | false,
  "has_faq": true | false,
  "has_process_explainer": true | false,
  "has_state_specific_guides": true | false,
  "has_video_content": true | false,
  "blog_post_count_estimate": 0-100,
  "language_coverage": ["English"],
  "gaps_identified": ["list of specific content gaps vs a comprehensive site"],
  "seo_opportunities": ["list of specific keyword/content opportunities they are missing"]
}}
"""


@dataclass
class ContentGapData:
    url: str
    document_coverage: dict = field(default_factory=dict)
    use_case_coverage: dict = field(default_factory=dict)
    content_depth: str = ""
    has_country_guides: bool = False
    has_faq: bool = False
    has_process_explainer: bool = False
    has_state_specific_guides: bool = False
    has_video_content: bool = False
    blog_post_count_estimate: int = 0
    language_coverage: list = field(default_factory=list)
    gaps_identified: list = field(default_factory=list)
    seo_opportunities: list = field(default_factory=list)
    coverage_score: int = 0  # 0–100 computed from doc + use case coverage
    error: str = ""

    def compute_score(self) -> None:
        doc_hits = sum(1 for v in self.document_coverage.values() if v)
        use_hits = sum(1 for v in self.use_case_coverage.values() if v)
        max_score = len(DOCUMENT_TYPES) + len(USE_CASES)
        self.coverage_score = int((doc_hits + use_hits) / max(max_score, 1) * 100)


def analyze(url: str, scraped) -> ContentGapData:
    if not config.OPENROUTER_API_KEY:
        return ContentGapData(url=url, error="OPENROUTER_API_KEY not set")

    markdown = getattr(scraped, "markdown", "") or ""
    if not markdown:
        return ContentGapData(url=url, error="No content available")

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://apostille-research-tool",
    }
    payload = {
        "model": config.OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"URL: {url}\n\nContent:\n{markdown[:6000]}"},
        ],
        "temperature": 0.1,
        "max_tokens": 1000,
    }

    try:
        resp = requests.post(OPENROUTER_ENDPOINT, json=payload, headers=headers, timeout=45)
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return ContentGapData(url=url, error=str(e))

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except Exception:
                return ContentGapData(url=url, error="Could not parse JSON")
        else:
            return ContentGapData(url=url, error="No JSON in response")

    data = ContentGapData(
        url=url,
        document_coverage=parsed.get("document_coverage", {}),
        use_case_coverage=parsed.get("use_case_coverage", {}),
        content_depth=parsed.get("content_depth", ""),
        has_country_guides=parsed.get("has_destination_country_guides", False),
        has_faq=parsed.get("has_faq", False),
        has_process_explainer=parsed.get("has_process_explainer", False),
        has_state_specific_guides=parsed.get("has_state_specific_guides", False),
        has_video_content=parsed.get("has_video_content", False),
        blog_post_count_estimate=int(parsed.get("blog_post_count_estimate", 0)),
        language_coverage=parsed.get("language_coverage", ["English"]),
        gaps_identified=parsed.get("gaps_identified", []),
        seo_opportunities=parsed.get("seo_opportunities", []),
    )
    data.compute_score()
    return data


def analyze_all(competitors: list, scraped_map: dict) -> dict[str, ContentGapData]:
    results: dict[str, ContentGapData] = {}
    total = len(competitors)
    for i, comp in enumerate(competitors, 1):
        scraped = scraped_map.get(comp.url)
        print(f"  [{i}/{total}] Content Gap: {comp.domain}")
        results[comp.url] = analyze(comp.url, scraped)
        cg = results[comp.url]
        if not cg.error:
            print(f"    ✓ Coverage={cg.coverage_score}% | Depth={cg.content_depth} | CountryGuides={cg.has_country_guides}")
        else:
            print(f"    ✗ {cg.error}")
    return results


def build_coverage_matrix(competitors: list, gap_map: dict) -> list[list]:
    """Build a document coverage matrix for the sheet."""
    domains = [c.domain for c in competitors]
    header = ["Document Type"] + domains
    rows = [header]
    for doc in DOCUMENT_TYPES:
        row = [doc]
        for comp in competitors:
            cg = gap_map.get(comp.url)
            if cg and cg.document_coverage:
                row.append("✓" if cg.document_coverage.get(doc, False) else "✗")
            else:
                row.append("")
        rows.append(row)
    return rows


def aggregate_gaps(gap_map: dict) -> list[str]:
    """Find content gaps that appear across MULTIPLE competitors — highest-opportunity topics."""
    gap_frequency: dict[str, int] = {}
    for cg in gap_map.values():
        for gap in cg.gaps_identified:
            gap_frequency[gap] = gap_frequency.get(gap, 0) + 1

    sorted_gaps = sorted(gap_frequency.items(), key=lambda x: x[1], reverse=True)
    return [f"{gap} (missing from {count} sites)" for gap, count in sorted_gaps[:10]]
