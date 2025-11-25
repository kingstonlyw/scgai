import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Optional .env loader (for OPENAI_API_KEY when --llm-title is used)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

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


def _llm_title(client, model: str, name: str, rephr: str) -> str:
    """Generate a concise project title from the rephrased submission.
    Returns a short string (<= 8 words). Falls back to a heuristic on failure.
    """
    prompt = (
        "Create a concise, specific project title (max 8 words).\n"
        "No quotes, no emojis, no trailing punctuation.\n"
        "Focus on the core task or workflow.\n"
        "Return ONLY the title text.\n\n"
        f"Name: {name}\n"
        f"Rephrased submission: {rephr}"
    )
    # Prefer Responses API
    try:
        resp = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": [{"type": "text", "text": "Return only a title line."}]},
                {"role": "user", "content": [{"type": "text", "text": prompt}]},
            ],
            temperature=0.2,
        )
        title = (resp.output_text or "").strip()
        return title.splitlines()[0][:120]
    except Exception:
        pass
    # Fallback: Chat Completions
    try:
        chat = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Return only a title line."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        title = (chat.choices[0].message.content or "").strip()
        return title.splitlines()[0][:120]
    except Exception:
        frag = rephr.split(".")[0].strip()
        return (frag or "Untitled")[0:120]


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Build front-facing JSON (name + rephrased_submission or LLM title) sorted by overall score."
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
    ap.add_argument(
        "--llm-title",
        action="store_true",
        help="Generate a concise LLM title instead of using rephrased_submission",
    )
    ap.add_argument(
        "--model",
        default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        help="Model to use when --llm-title is set",
    )
    args = ap.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    if not in_path.exists():
        raise SystemExit(f"Input not found: {in_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    data: List[Dict[str, Any]] = json.load(open(in_path, encoding="utf-8"))

    # Optional LLM client
    client = None
    if args.llm_title:
        try:
            from openai import OpenAI  # type: ignore
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise SystemExit("--llm-title requires OPENAI_API_KEY (set in .env or environment)")
            client = OpenAI(api_key=api_key)
        except Exception as e:
            raise SystemExit(f"Failed to init OpenAI client for --llm-title: {e}")

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
        if args.llm_title:
            title = _llm_title(client, args.model, name, rephr)
            item: Dict[str, Any] = {"name": name, "title": title}
        else:
            item = {"name": name, "rephrased_submission": rephr}
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
