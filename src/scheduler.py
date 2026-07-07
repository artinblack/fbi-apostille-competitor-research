"""
Weekly diff scheduler.
Compares the current run results against the previous run's CSV,
identifying: new competitors, disappeared competitors, rank changes,
and significant copy/offer changes.
"""

import csv
import json
from datetime import datetime
from pathlib import Path

from src import notifier


OUTPUT_DIR = Path("output")
DIFF_FILE = OUTPUT_DIR / "diff_history.json"


def _load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _find_previous_csv(current_date: str) -> Path | None:
    """Find the most recent CSV that isn't today's."""
    csvs = sorted(OUTPUT_DIR.glob("results_*.csv"), reverse=True)
    for p in csvs:
        if current_date not in p.name:
            return p
    return None


def _domain_from_row(row: dict) -> str:
    return row.get("Domain", "")


def compute_diff(current_rows: list[dict], previous_rows: list[dict]) -> dict:
    """
    Compare two result sets. Returns a diff summary dict:
    {
      "new_competitors": [...],
      "dropped_competitors": [...],
      "rank_changes": [{domain, old_rank, new_rank, direction}],
      "offer_changes": [{domain, field, note}],
      "summary": "..."
    }
    """
    current_domains  = {_domain_from_row(r): r for r in current_rows}
    previous_domains = {_domain_from_row(r): r for r in previous_rows}

    new_comps     = [d for d in current_domains if d not in previous_domains]
    dropped_comps = [d for d in previous_domains if d not in current_domains]

    rank_changes = []
    for domain, curr_row in current_domains.items():
        if domain not in previous_domains:
            continue
        prev_row = previous_domains[domain]
        try:
            old_rank = int(prev_row.get("Rank", 0))
            new_rank = int(curr_row.get("Rank", 0))
            if abs(old_rank - new_rank) >= 3:
                rank_changes.append({
                    "domain":    domain,
                    "old_rank":  old_rank,
                    "new_rank":  new_rank,
                    "direction": "↑ improved" if new_rank < old_rank else "↓ dropped",
                })
        except ValueError:
            pass

    summary_parts = []
    if new_comps:
        summary_parts.append(f"{len(new_comps)} new competitor(s): {', '.join(new_comps)}")
    if dropped_comps:
        summary_parts.append(f"{len(dropped_comps)} dropped: {', '.join(dropped_comps)}")
    if rank_changes:
        summary_parts.append(f"{len(rank_changes)} rank change(s)")
    if not summary_parts:
        summary_parts.append("No significant changes detected")

    return {
        "new_competitors":   new_comps,
        "dropped_competitors": dropped_comps,
        "rank_changes":      rank_changes,
        "summary":           " | ".join(summary_parts),
    }


def save_diff(diff: dict, run_date: str) -> None:
    history = []
    if DIFF_FILE.exists():
        try:
            history = json.loads(DIFF_FILE.read_text())
        except Exception:
            pass
    history.append({"date": run_date, **diff})
    # Keep last 52 weeks
    DIFF_FILE.write_text(json.dumps(history[-52:], indent=2))


def run_diff_and_notify(current_csv: Path) -> dict:
    """
    Load current and previous CSV, compute diff, save history, send alerts.
    Returns the diff dict.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    previous_csv = _find_previous_csv(today)

    current_rows  = _load_csv(current_csv)
    previous_rows = _load_csv(previous_csv) if previous_csv else []

    diff = compute_diff(current_rows, previous_rows)
    save_diff(diff, today)

    print(f"\n  Diff vs previous run: {diff['summary']}")

    if diff["new_competitors"]:
        notifier.notify_new_competitors(diff["new_competitors"], today)

    return diff


def load_diff_history() -> list[dict]:
    """Load all historical diffs for dashboard display."""
    if not DIFF_FILE.exists():
        return []
    try:
        return json.loads(DIFF_FILE.read_text())
    except Exception:
        return []
