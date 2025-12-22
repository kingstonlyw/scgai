"""Generate `output/ranked_submissions.json` from `output/front_facing.json`.

Produces an object with:
- "monthly": mapping YYYY-MM to top submission for that month
- "Year to Date": the full list from front_facing.json

Usage:
  python rank_submissions.py --input output/front_facing.json --output output/ranked_submissions.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def parse_iso_month(iso_ts: str) -> Optional[str]:
    """
    Redundant function to convert input date to dt. Defaults to None if input is not a valid date.
    """
    if not iso_ts:
        return None
    try:
        dt = datetime.fromisoformat(iso_ts)
    except Exception:
        try:
            dt = datetime.strptime(iso_ts.split("+")[0], "%Y-%m-%dT%H:%M:%S")
        except Exception:
            return None
    return f"{dt.year:04d}-{dt.month:02d}"


def month_range(start: str, end: str) -> List[str]:
    sy, sm = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    months = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def choose_top(subs: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Choose most recent by completion_time
    def ts_key(rr: Dict[str, Any]):
        t = rr.get("completion_time") or ""
        try:
            return datetime.fromisoformat(t)
        except Exception:
            try:
                return datetime.strptime(t.split("+")[0], "%Y-%m-%dT%H:%M:%S")
            except Exception:
                return datetime.min

    return max(subs, key=ts_key)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="output/front_facing.json", help="Path to front_facing JSON list")
    p.add_argument("--output", default="output/ranked_submissions.json", help="Output ranked JSON path")
    p.add_argument("--start-month", help="Start month YYYY-MM (defaults to earliest submission month)")
    args = p.parse_args()

    inp = Path(args.input)
    if not inp.exists():
        raise SystemExit(f"Input file not found: {inp}")

    with open(inp, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise SystemExit("Expected input JSON to be a list of submissions")

    groups: Dict[str, List[Dict[str, Any]]] = {}
    months_present: List[str] = []
    for rec in data:
        cm = parse_iso_month(rec.get("completion_time") or "")
        if not cm:
            continue
        groups.setdefault(cm, []).append(rec)
        if cm not in months_present:
            months_present.append(cm)

    if not months_present:
        raise SystemExit("No submissions with parsable completion_time found")

    months_present.sort()
    start_month = args.start_month or months_present[0]
    try:
        _ = list(map(int, start_month.split("-")))
    except Exception:
        raise SystemExit("--start-month must be in YYYY-MM format")

    last_month = months_present[-1]
    months = month_range(start_month, last_month)

    monthly_map: Dict[str, Dict[str, Any]] = {}
    for m in months:
        subs = groups.get(m)
        if not subs:
            continue
        monthly_map[m] = choose_top(subs)

    out_obj = {"monthly": monthly_map, "Year to Date": data}

    outp = Path(args.output)
    outp.parent.mkdir(parents=True, exist_ok=True)
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(out_obj, f, ensure_ascii=False, indent=2)

    print(f"Wrote {outp} with {len(monthly_map)} monthly entries and {len(data)} total submissions")


if __name__ == "__main__":
    main()
