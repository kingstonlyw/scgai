import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def _coerce_score(v: Any) -> int:
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
    prompt = (
        "Create a concise, specific project title (max 8 words).\n"
        "No quotes, no emojis, no trailing punctuation.\n"
        "Focus on the core task or workflow.\n"
        "Return ONLY the title text.\n\n"
        f"Name: {name}\n"
        f"Rephrased submission: {rephr}"
    )
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


def _norm_id(v: Any) -> str:
    try:
        f = float(v)
        if f.is_integer():
            return str(int(f))
        return str(v)
    except Exception:
        return str(v)


def _pick_optional_field(rec: Dict[str, Any]) -> str:
    return (
        rec.get("demo_link_or_screenshot")
        or rec.get("Optional:\u00a0Upload a screenshot or paste a link to a demo")
        or rec.get("Optional: Upload a screenshot or paste a link to a demo")
        or ""
    )


def _llm_clean_fields(client, model: str, fields: Dict[str, Any]) -> Dict[str, str]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "what_built": {"type": "string", "maxLength": 600},
            "challenge_addressed": {"type": "string", "maxLength": 600},
            "outcome": {"type": "string", "maxLength": 600},
            "cross_team_use": {"type": "string", "maxLength": 600},
            "surprise": {"type": "string", "maxLength": 600},
            "optional": {"type": "string", "maxLength": 600},
        },
        "required": [
            "what_built",
            "challenge_addressed",
            "outcome",
            "cross_team_use",
            "surprise",
            "optional",
        ],
    }

    def _safe(text: str) -> Dict[str, Any]:
        t = text.strip()
        if t.startswith("```"):
            t = "\n".join(ln for ln in t.splitlines() if not ln.strip().startswith("```")).strip()
        return json.loads(t or "{}")

    prompt = (
        "Clean and standardize each field into clear, concise text (1–3 sentences each).\n"
        "Preserve meaning, remove filler and redundant phrasing.\n"
        "If a field is empty, return an empty string for that key.\n"
        "Return ONLY JSON with EXACT keys: what_built, challenge_addressed, outcome, cross_team_use, surprise, optional.\n\n"
        f"Input JSON:\n{json.dumps(fields, ensure_ascii=False)}"
    )

    try:
        resp = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": [{"type": "text", "text": "Return only valid JSON per schema."}]},
                {"role": "user", "content": [{"type": "text", "text": prompt}]},
            ],
            response_format={"type": "json_schema", "json_schema": {"name": "CleanedFields", "schema": schema, "strict": True}},
            temperature=0.2,
        )
        return _safe(resp.output_text)
    except Exception:
        pass
    try:
        chat = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Return only valid JSON per schema."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        return _safe(chat.choices[0].message.content or "{}")
    except Exception:
        return {k: (fields.get(k) or "").strip() for k in [
            "what_built","challenge_addressed","outcome","cross_team_use","surprise","optional"
        ]}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Build front-facing JSON (name + rephrased or LLM title), with optional LLM-cleaned fields, sorted by overall score."
    )
    ap.add_argument("--input", default="scgai/AI Challenge/output/evaluations.json", help="Path to evaluations.json")
    ap.add_argument("--output", default="scgai/AI Challenge/output/front_facing.json", help="Output front-facing JSON path")
    ap.add_argument("--include-score", action="store_true", help="Include overall_score in items")
    ap.add_argument("--llm-title", action="store_true", help="Generate concise LLM title instead of rephrased_submission")
    ap.add_argument("--llm-clean", action="store_true", help="Clean key fields with LLM and embed under 'cleaned'")
    ap.add_argument("--submissions", default="scgai/AI Challenge/output/submissions.json", help="Path to submissions.json (for --llm-clean)")
    ap.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), help="Model when LLM features enabled")
    args = ap.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    if not in_path.exists():
        raise SystemExit(f"Input not found: {in_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    evals: List[Dict[str, Any]] = json.load(open(in_path, encoding="utf-8"))

    client = None
    if args.llm_title or args.llm_clean:
        try:
            from openai import OpenAI  # type: ignore
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise SystemExit("LLM features require OPENAI_API_KEY (set in .env or environment)")
            client = OpenAI(api_key=api_key)
        except Exception as e:
            raise SystemExit(f"Failed to init OpenAI client: {e}")

    subs_by_id: Dict[str, Dict[str, Any]] = {}
    spath = Path(args.submissions)
    if spath.exists():
        subs: List[Dict[str, Any]] = json.load(open(spath, encoding="utf-8"))
        for s in subs:
            subs_by_id[_norm_id(s.get("id"))] = s
    elif args.llm_clean:
        raise SystemExit(f"--llm-clean requires submissions file: {spath}")

    ranked: List[Tuple[int, str, Dict[str, Any]]] = []
    for ev in evals:
        if not isinstance(ev, dict) or ev.get("error"):
            continue
        meta = ev.get("submission_metadata") or {}
        name = (meta.get("name") or "").strip()
        rephr = (ev.get("rephrased_submission") or "").strip()
        overall = _coerce_score((ev.get("scores") or {}).get("overall_verdict"))
        if not name and not rephr:
            continue


        sid = _norm_id((ev.get("_id") or meta.get("submission_id")))
        src = subs_by_id.get(sid)

        if args.llm_title and client is not None:
            title = _llm_title(client, args.model, name, rephr)
            item: Dict[str, Any] = {"name": name, "title": title}
        else:
            item = {"name": name, "rephrased_submission": rephr}
        item.update(
            {
                "submission_id": sid,
                "completion_time": meta.get("timestamp_utc"),
                "email": meta.get("email") or (src or {}).get("email"),
                "submitter_type": meta.get("submitter_type") or (src or {}).get("submitter_type"),
                "team_or_department": meta.get("team_or_department") or (src or {}).get("team_or_department"),
            }
        )


        if args.llm_clean and client is not None:
            if src:
                fields = {
                    "what_built": (src.get("what_built") or "").strip(),
                    "challenge_addressed": (src.get("challenge_addressed") or "").strip(),
                    "outcome": (src.get("outcome") or "").strip(),
                    "cross_team_use": (src.get("cross_team_use") or "").strip(),
                    "surprise": (src.get("surprise") or "").strip(),
                    "optional": str(_pick_optional_field(src)).strip(),
                }
                cleaned = _llm_clean_fields(client, args.model, fields)
                item["cleaned"] = cleaned

        if args.include_score:
            item["overall_score"] = overall
        ranked.append((overall, name.lower(), item))

    ranked.sort(key=lambda x: (-x[0], x[1]))
    output_items = [t[2] for t in ranked]

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output_items, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(output_items)} items to {out_path}")


if __name__ == "__main__":
    main()
