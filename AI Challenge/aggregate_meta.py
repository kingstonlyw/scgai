import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _norm_id(v: Any) -> str:
    if isinstance(v, (int, str)):
        try:
            # Normalize numeric strings like "1.0" to "1"
            f = float(v)
            if f.is_integer():
                return str(int(f))
            return str(v)
        except Exception:
            return str(v)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else str(v)
    return str(v)


def _parse_date(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
        return dt.date().isoformat()
    except Exception:
        return None


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    ap = argparse.ArgumentParser(description="Aggregate meta statistics from evaluations.json")
    ap.add_argument("--evaluations", default="output/evaluations.json", help="Path to evaluations.json")
    ap.add_argument("--submissions", default="output/submissions.json", help="Path to submissions.json (for team/type/link stats)")
    ap.add_argument("--output", default="output/meta.json", help="Path to write meta JSON")
    args = ap.parse_args()

    eval_path = Path(args.evaluations)
    sub_path = Path(args.submissions)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not eval_path.exists():
        raise SystemExit(f"Evaluations file not found: {eval_path}")

    evaluations: List[Dict[str, Any]] = load_json(eval_path)

    submissions_by_id: Dict[str, Dict[str, Any]] = {}
    if sub_path.exists():
        # submissions.json is an array of cleaned records
        for rec in load_json(sub_path):
            submissions_by_id[_norm_id(rec.get("id"))] = rec

    # Accumulators
    response_count = 0
    overall_hist = Counter()
    score_sums: Dict[str, float] = defaultdict(float)
    score_counts: Dict[str, int] = defaultdict(int)
    by_submitter_type = Counter()
    by_team = Counter()
    by_day = Counter()
    has_demo, no_demo = 0, 0

    score_fields = [
        "specificity",
        "strategic_alignment",
        "value_roi",
        "feasibility",
        "non_technical_usability",
        "novelty_creativity",
        "technical_complexity_vs_value",
        "overall_verdict",
    ]

    for ev in evaluations:
        if not isinstance(ev, dict) or ev.get("error"):
            continue
        scores = ev.get("scores") or {}
        # Parse numeric strings 1..5
        parsed: Dict[str, float] = {}
        for k in score_fields:
            try:
                v = scores.get(k)
                n = int(str(v))
                if 1 <= n <= 5:
                    parsed[k] = float(n)
            except Exception:
                pass
        if not parsed:
            continue

        response_count += 1

        # Sums for averages
        for k, n in parsed.items():
            score_sums[k] += n
            score_counts[k] += 1

        # Overall histogram 
        if "overall_verdict" in parsed:
            overall_hist[str(int(parsed["overall_verdict"]))] += 1

        # Join with submission for type/team/link and day
        sid = _norm_id(ev.get("_id") or ev.get("submission_metadata", {}).get("submission_id"))
        sub = submissions_by_id.get(sid, {})
        stype = sub.get("submitter_type")
        if stype:
            by_submitter_type[str(stype)] += 1
        team = sub.get("team_or_department")
        if team:
            by_team[str(team)] += 1

        demo = sub.get("demo_link_or_screenshot") or sub.get("Optional:\u00a0Upload a screenshot or paste a link to a demo")
        if demo and str(demo).strip():
            has_demo += 1
        else:
            no_demo += 1

        ts = ev.get("submission_metadata", {}).get("timestamp_utc")
        d = _parse_date(ts)
        if d:
            by_day[d] += 1

    # Averages
    averages = {k: round(_mean([score_sums[k] / score_counts[k] if score_counts[k] else 0]), 3) for k in score_fields}
    # Overall mean of means
    overall_avg = round(_mean([v for k, v in averages.items() if k != "overall_verdict"]), 3)

    # Sort distributions
    by_team_sorted = sorted(({"team": t, "count": c} for t, c in by_team.items()), key=lambda x: (-x["count"], x["team"]))
    by_day_sorted = sorted(({"date": d, "count": c} for d, c in by_day.items()), key=lambda x: x["date"])

    meta: Dict[str, Any] = {
        "schema_version": "1.0",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "counts": {
            "responses_evaluated": response_count,
            "submissions_total": len(submissions_by_id) if submissions_by_id else None,
        },
        "averages": averages | {"overall_mean": overall_avg},
        "distributions": {
            "overall_verdict_histogram": {k: overall_hist.get(k, 0) for k in ["1","2","3","4","5"]},
            "by_submitter_type": dict(by_submitter_type),
            "by_team": by_team_sorted,
            "by_day": by_day_sorted,
            "link_presence": {"has_demo_link": has_demo, "no_demo_link": no_demo},
        },
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"Wrote meta statistics to {out_path}")


if __name__ == "__main__":
    main()
