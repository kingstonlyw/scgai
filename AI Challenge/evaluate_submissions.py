import os
import sys
import json
import time
from pathlib import Path
from typing import Any, Dict, List

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


INPUT_PATH = Path("output/submissions.json")
OUTPUT_PATH = Path("output/evaluations.json")



SCORES_ENUM = ["1", "2", "3", "4", "5"]

EVAL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "submission_metadata": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"},
                "submission_id": {"type": "string"},
                "timestamp_utc": {"type": "string"},
            },
            "required": ["name", "email", "submission_id", "timestamp_utc"],
        },
        "rephrased_submission": {"type": "string", "maxLength": 1200},
        "reasoning": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "specificity": {"type": "string", "maxLength": 300},
                "strategic_alignment": {"type": "string", "maxLength": 300},
                "value_roi": {"type": "string", "maxLength": 300},
                "feasibility": {"type": "string", "maxLength": 300},
                "non_technical_usability": {"type": "string", "maxLength": 300},
                "novelty_creativity": {"type": "string", "maxLength": 300},
                "technical_complexity_vs_value": {"type": "string", "maxLength": 300},
                "overall_verdict": {"type": "string", "maxLength": 300},
            },
            "required": [
                "specificity",
                "strategic_alignment",
                "value_roi",
                "feasibility",
                "non_technical_usability",
                "novelty_creativity",
                "technical_complexity_vs_value",
                "overall_verdict",
            ],
        },
        "scores": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "specificity": {"type": "string", "enum": SCORES_ENUM},
                "strategic_alignment": {"type": "string", "enum": SCORES_ENUM},
                "value_roi": {"type": "string", "enum": SCORES_ENUM},
                "feasibility": {"type": "string", "enum": SCORES_ENUM},
                "non_technical_usability": {"type": "string", "enum": SCORES_ENUM},
                "novelty_creativity": {"type": "string", "enum": SCORES_ENUM},
                "technical_complexity_vs_value": {"type": "string", "enum": SCORES_ENUM},
                "overall_verdict": {"type": "string", "enum": SCORES_ENUM},
            },
            "required": [
                "specificity",
                "strategic_alignment",
                "value_roi",
                "feasibility",
                "non_technical_usability",
                "novelty_creativity",
                "technical_complexity_vs_value",
                "overall_verdict",
            ],
        },
        "implementation_roadmap": {"type": "string", "maxLength": 2000},
    },
    "required": [
        "submission_metadata",
        "rephrased_submission",
        "reasoning",
        "scores",
        "implementation_roadmap",
    ],
}

# eventually switch for Lizzie's prompt
SYSTEM_PROMPT = (
    "You are an AI Proposal Evaluator for an Asset Management firm’s internal innovation challenge.\n\n"
    "Your job is to critically assess each submission for clarity, relevance, and potential impact on the firm’s strategy. \n"
    "Respond using structured bullet points and a consistent format.\n\n"
    "Be blunt, objective, and concise. Do not praise generic ideas or use vague language. "
    "Always comment on every criterion, even if information is missing.\n\n"
    "Word limit: Maximum 120 words total (each bullet ≤ 25 words).\n\n"
    "Evaluate the submission using the following categories:\n"
    "Specificity: Is the idea narrow and task-focused? Does it clearly define what AI is doing?\n"
    "Strategic Alignment: Does it directly support asset management functions (e.g., acquisitions, underwriting, risk, client service)?\n"
    "Value & ROI: Does it deliver measurable business value (cost savings, improved decisions, faster workflows)? Can this idea be used in other departments?\n"
    "Feasibility: Can it realistically be built using current data, infrastructure, or Microsoft/PowerAutomate tools?\n"
    "Non-Technical Usability: Would non-technical users (analysts, portfolio managers) easily understand and use it?\n"
    "Novelty & Creativity: Is this idea unique or just a generic AI application with minimal differentiation from existing ideas?\n"
    "Technical Complexity vs Added Value: How much technical effort would go into implementing this submission. Does the added value justify the resources needed?\n"
    "Overall Verdict: In 1–2 sentences, bluntly summarize how valuable or irrelevant this idea is to Starwood.\n\n"
    "Return your evaluation ONLY as JSON conforming to the provided schema. "
    "Scores MUST be numeric strings '1'..'5' (no words). 5 = best. "
    "Use brief bullet-style sentences in the reasoning fields. Keep total words ≤120 and each bullet ≤25 words."
)


def build_user_payload(rec: Dict[str, Any]) -> Dict[str, Any]:
    demo = rec.get("demo_link_or_screenshot") or rec.get("Optional:\u00a0Upload a screenshot or paste a link to a demo")
    return {
        "id": rec.get("id"),
        "name": rec.get("name"),
        "email": rec.get("email"),
        "start_time": rec.get("start_time"),
        "completion_time": rec.get("completion_time"),
        "submitter_type": rec.get("submitter_type"),
        "team_or_department": rec.get("team_or_department"),
        "what_built": rec.get("what_built"),
        "challenge_addressed": rec.get("challenge_addressed"),
        "outcome": rec.get("outcome"),
        "cross_team_use": rec.get("cross_team_use"),
        "surprise": rec.get("surprise"),
        "demo_links": demo,
    }


def _safe_json_loads(text: str) -> Dict[str, Any]:
    t = text.strip()
    if t.startswith("```"):
        # Strip code fences if the model returns them
        t = "\n".join(
            line for line in t.splitlines() if not line.strip().startswith("```")
        ).strip()
    return json.loads(t)


def call_model(client: OpenAI, payload: Dict[str, Any], model: str) -> Dict[str, Any]:
    """Call model using Responses API if available; otherwise fall back to Chat Completions.

    Returns parsed JSON dict adhering to EVAL_SCHEMA.
    """
    # Prefer Responses API
    try:
        resp = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Submission JSON:\n" + json.dumps(payload, ensure_ascii=False),
                        }
                    ],
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "SubmissionEvaluation",
                    "schema": EVAL_SCHEMA,
                    "strict": True,
                },
            },
            temperature=0.2,
        )
        return _safe_json_loads(resp.output_text)
    except TypeError:
        pass
    except AttributeError:
        pass

    # Fallback: Chat Completions with JSON schema (or json_object)
    try:
        chat = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "Submission JSON:\n" + json.dumps(payload, ensure_ascii=False),
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "SubmissionEvaluation",
                    "schema": EVAL_SCHEMA,
                    "strict": True,
                },
            },
            temperature=0.2,
        )
        text = chat.choices[0].message.content or "{}"
        return _safe_json_loads(text)
    except APIError:
        raise
    except Exception:
        # Last resort: try json_object
        chat = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "Return ONLY valid JSON matching the schema.\n\nSubmission JSON:\n"
                    + json.dumps(payload, ensure_ascii=False),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        text = chat.choices[0].message.content or "{}"
        return _safe_json_loads(text)


def _coerce_score(value: Any) -> str:
    if value is None:
        return "3"
    # Accept ints or numeric strings
    try:
        n = int(str(value).strip())
        if 1 <= n <= 5:
            return str(n)
    except Exception:
        pass
    # Map common words in case LLM doesn't follow number directoins
    v = str(value).strip().lower()
    mappings = {
        "very low": "1",
        "low": "2",
        "medium": "3",
        "avg": "3",
        "average": "3",
        "moderate": "3",
        "high": "4",
        "very high": "5",
        "excellent": "5",
        "poor": "1",
        "fair": "2",
        "good": "4",
        "great": "5",
    }
    return mappings.get(v, "3")


def _normalize_scores(evaluation: Dict[str, Any]) -> Dict[str, Any]:
    scores = evaluation.get("scores")
    if not isinstance(scores, dict):
        return evaluation
    fields = [
        "specificity",
        "strategic_alignment",
        "value_roi",
        "feasibility",
        "non_technical_usability",
        "novelty_creativity",
        "technical_complexity_vs_value",
        "overall_verdict",
    ]
    normalized = {}
    for k in fields:
        normalized[k] = _coerce_score(scores.get(k))
    evaluation["scores"] = normalized
    return evaluation


def main() -> None:
    if not INPUT_PATH.exists():
        print(f"Input not found: {INPUT_PATH}", file=sys.stderr)
        sys.exit(1)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Missing OPENAI_API_KEY. Set it in your environment or .env file.", file=sys.stderr)
        sys.exit(2)

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)

    records: List[Dict[str, Any]] = json.load(open(INPUT_PATH, encoding="utf-8"))
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    to_process = records[:limit] if limit else records

    results: List[Dict[str, Any]] = []
    for i, rec in enumerate(to_process, 1):
        payload = build_user_payload(rec)
        metadata = {
            "name": rec.get("name") or "",
            "email": rec.get("email") or "",
            "submission_id": str(rec.get("id")),
            "timestamp_utc": rec.get("completion_time") or rec.get("start_time") or "",
        }

        for attempt in range(4):
            try:
                evaluation = call_model(client, payload, model=model)
                evaluation = _normalize_scores(evaluation)
                evaluation["submission_metadata"] = metadata
                results.append(evaluation | {"_id": rec.get("id")})
                break
            except (RateLimitError, APIError) as e:
                wait = 2 ** attempt
                print(f"[{i}/{len(to_process)}] retry in {wait}s: {e}", file=sys.stderr)
                time.sleep(wait)
            except Exception as e:
                print(f"[{i}/{len(to_process)}] failed: {e}", file=sys.stderr)
                results.append({"_id": rec.get("id"), "error": str(e)})
                break

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(results)} evaluations to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
