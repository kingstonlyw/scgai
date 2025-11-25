import os
import sys
import json
import time
from pathlib import Path
from typing import Any, Dict, List

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from openai import OpenAI, APIError, RateLimitError
except Exception as e:
    print("Missing dependency: openai. Install with: python -m pip install --user -r requirements-openai.txt", file=sys.stderr)
    raise


BASE = Path(__file__).parent
EVAL_PATH = BASE / "output" / "evaluations.json"
OUT_PER_SUB = BASE / "output" / "keywords.json"
OUT_AGG = BASE / "output" / "keywords_agg.json"


SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "keywords": {
            "type": "array",
            "minItems": 3,
            "maxItems": 16,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "term": {"type": "string"},
                    "weight": {"type": "number"}
                },
                "required": ["term"]
            }
        }
    },
    "required": ["keywords"]
}

PROMPT = (
    "Extract 5–12 concise, domain‑specific keywords (1–3 words each) that capture the core idea.\n"
    "Avoid generic or filler words (e.g., 'using', 'data', 'system', 'improve').\n"
    "Prefer terms meaningful for an asset management firm (workflows, tools, domains).\n"
    "Return ONLY JSON per the provided schema."
)


def _safe_json(text: str) -> Dict[str, Any]:
    t = text.strip()
    if t.startswith("```"):
        t = "\n".join([ln for ln in t.splitlines() if not ln.strip().startswith("```")]).strip()
    return json.loads(t or "{}")


def call_model(client: OpenAI, model: str, content: Dict[str, Any]) -> Dict[str, Any]:
    # Prefer Responses API if available
    try:
        resp = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": [{"type": "text", "text": PROMPT}]},
                {"role": "user", "content": [{"type": "text", "text": json.dumps(content, ensure_ascii=False)}]},
            ],
            response_format={"type": "json_schema", "json_schema": {"name": "Keywords", "schema": SCHEMA, "strict": True}},
            temperature=0.1,
        )
        return _safe_json(resp.output_text)
    except Exception:
        pass

    # Fallback to Chat Completions
    try:
        chat = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": json.dumps(content, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        return _safe_json(chat.choices[0].message.content or "{}")
    except Exception as e:
        raise e


def main() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Missing OPENAI_API_KEY. Create .env or export the variable.", file=sys.stderr)
        sys.exit(2)

    if not EVAL_PATH.exists():
        print(f"Missing evaluations: {EVAL_PATH}", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    evaluations: List[Dict[str, Any]] = json.load(open(EVAL_PATH, encoding="utf-8"))
    per_sub: List[Dict[str, Any]] = []

    for i, ev in enumerate(evaluations, 1):
        if not isinstance(ev, dict) or ev.get("error"):
            continue
        meta = ev.get("submission_metadata") or {}
        name = meta.get("name") or ""
        sid = str(meta.get("submission_id") or ev.get("_id"))
        rephr = ev.get("rephrased_submission") or ""
        if not rephr:
            continue
        payload = {"id": sid, "name": name, "rephrased_submission": rephr}

        for attempt in range(4):
            try:
                out = call_model(client, model, payload)
                kws = out.get("keywords") or []
                # Normalize
                normalized = []
                for k in kws:
                    if isinstance(k, dict) and k.get("term"):
                        term = str(k["term"]).strip()
                        if term:
                            w = k.get("weight")
                            try:
                                weight = float(w) if w is not None else 1.0
                            except Exception:
                                weight = 1.0
                            normalized.append({"term": term, "weight": weight})
                    elif isinstance(k, str):
                        term = k.strip()
                        if term:
                            normalized.append({"term": term, "weight": 1.0})

                if normalized:
                    per_sub.append({"id": sid, "name": name, "keywords": normalized})
                break
            except (RateLimitError, APIError) as e:
                time.sleep(2 ** attempt)
            except Exception as e:
                # Record error and continue
                per_sub.append({"id": sid, "name": name, "error": str(e)})
                break

    # Write per-submission keywords
    OUT_PER_SUB.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PER_SUB, "w", encoding="utf-8") as f:
        json.dump(per_sub, f, ensure_ascii=False, indent=2)

    
    agg: Dict[str, Dict[str, Any]] = {}
    for row in per_sub:
        if not isinstance(row, dict) or row.get("error"):
            continue
        for kw in row.get("keywords", []):
            term = kw.get("term")
            weight = float(kw.get("weight") or 1.0)
            if not term:
                continue
            if term not in agg:
                agg[term] = {"term": term, "count": 0, "weight_sum": 0.0}
            agg[term]["count"] += 1
            agg[term]["weight_sum"] += weight

    agg_list = sorted(agg.values(), key=lambda x: (-x["count"], -x["weight_sum"], x["term"]))
    with open(OUT_AGG, "w", encoding="utf-8") as f:
        json.dump(agg_list, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(per_sub)} per-submission keywords to {OUT_PER_SUB}")
    print(f"Wrote {len(agg_list)} aggregated keywords to {OUT_AGG}")


if __name__ == "__main__":
    main()
