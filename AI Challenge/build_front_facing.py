import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

# sometimes LLM doesn't follow instructions and puts score as words instead of numbers
def _coerce_score(v: Any) -> int:
    """Coerce score to 1..5. Accept ints/strings and common words as fallback."""
    try:
        n = int(str(v).strip())
        if 1 <= n <= 5:
            return n
    except Exception:
        pass
    mapping = {
        "very low": 1,
        "low": 2,
        "medium": 3,
        "avg": 3,
        "average": 3,
        "moderate": 3,
        "high": 4,
        "very high": 5,
        "excellent": 5,
        "poor": 1,
        "fair": 2,
        "good": 4,
        "great": 5,
    }
    return mapping.get(str(v).strip().lower(), 3)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Build front-facing JSON (name + rephrased_submission) sorted by overall score."
    )
    ap.add_argument(
        "--input",
        default="scgai/AI Challenge/output/evaluations.json",
        help="Path to evaluations.json",
    )
    ap.add_argument(
        "--output",
        default="scgai/AI Challenge/output/front_facing.json",
        help="Path to write the front-facing JSON",
    )
    ap.add_argument(
        "--include-score",
        action="store_true",
        help="Include overall_score in output items",
    )
    args = ap.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    if not in_path.exists():
        raise SystemExit(f"Input not found: {in_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    data: List[Dict[str, Any]] = json.load(open(in_path, encoding="utf-8"))

    ranked: List[Tuple[int, str, Dict[str, Any]]] = []
    for ev in data:
        if not isinstance(ev, dict) or ev.get("error"):
            continue
        meta = ev.get("submission_metadata") or {}
        name = (meta.get("name") or "").strip()
        rephr = (ev.get("rephrased_submission") or "").strip()
        overall = _coerce_score((ev.get("scores") or {}).get("overall_verdict"))
        if not name and not rephr:
            continue
        item: Dict[str, Any] = {"name": name, "rephrased_submission": rephr}
        if args.include_score:
            item["overall_score"] = overall
        ranked.append((overall, name.lower(), item))

    # Sort by score desc, then name
    ranked.sort(key=lambda x: (-x[0], x[1]))
    output_items = [t[2] for t in ranked]

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output_items, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(output_items)} items to {out_path}")


if __name__ == "__main__":
    main()
