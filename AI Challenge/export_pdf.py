import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

REPORTLAB_AVAILABLE = True
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        PageBreak,
        ListFlowable,
        ListItem,
    )
    from reportlab.pdfbase.pdfmetrics import stringWidth
except Exception:
    REPORTLAB_AVAILABLE = False


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


def _stars(n: int) -> str:
    return "★" * n + "☆" * (5 - n)


def _build_story(data: List[Dict[str, Any]], title: str) -> List[Any]:
    styles = getSampleStyleSheet()
    h1 = styles["Heading1"]
    h2 = styles["Heading2"]
    h3 = styles["Heading3"]
    body = styles["BodyText"]

    small = ParagraphStyle("small", parent=body, fontSize=9, leading=12)
    grey = ParagraphStyle("grey", parent=body, textColor=colors.grey)
    bullet_style = ParagraphStyle("bullet", parent=body, leftIndent=12)

    story: List[Any] = []
    story.append(Paragraph(title, h1))
    story.append(Spacer(1, 6))

    # Sort by overall score desc, then name ascending
    ranked: List[Dict[str, Any]] = []
    for ev in data:
        if not isinstance(ev, dict) or ev.get("error"):
            continue
        scores = ev.get("scores") or {}
        overall = _coerce_score(scores.get("overall_verdict"))
        ev["__overall"] = overall
        ranked.append(ev)
    ranked.sort(key=lambda r: (-r.get("__overall", 0), (r.get("submission_metadata") or {}).get("name", "")))

    for idx, ev in enumerate(ranked, 1):
        meta = ev.get("submission_metadata") or {}
        name = meta.get("name", "")
        email = meta.get("email", "")
        sid = meta.get("submission_id", "")
        ts = meta.get("timestamp_utc", "")
        rephr = (ev.get("rephrased_submission") or "").strip()
        scores = ev.get("scores") or {}
        reasoning = ev.get("reasoning") or {}
        roadmap = (ev.get("implementation_roadmap") or "").strip()
        overall = ev.get("__overall", 0)

        story.append(Paragraph(f"{idx}. {name}", h2))
        story.append(Paragraph(f"Overall: {_stars(overall)} ({overall}/5)", h3))
        story.append(Paragraph(f"ID: {sid} | {email} | {ts}", small))
        story.append(Spacer(1, 6))

        if rephr:
            story.append(Paragraph("Rephrased Submission", h3))
            story.append(Paragraph(rephr.replace("\n", "<br/>"), body))
            story.append(Spacer(1, 6))

        # Scores table
        table_rows = [["Category", "Score (1-5)"]]
        for k in [
            "specificity",
            "strategic_alignment",
            "value_roi",
            "feasibility",
            "non_technical_usability",
            "novelty_creativity",
            "technical_complexity_vs_value",
            "overall_verdict",
        ]:
            s = _coerce_score((scores or {}).get(k))
            label = k.replace("_", " ").title()
            table_rows.append([label, f"{s}"])

        t = Table(table_rows, hAlign="LEFT", colWidths=[220, 80])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ]
            )
        )
        story.append(t)
        story.append(Spacer(1, 8))

        # Reasoning bullets
        bullets = []
        for k in [
            "specificity",
            "strategic_alignment",
            "value_roi",
            "feasibility",
            "non_technical_usability",
            "novelty_creativity",
            "technical_complexity_vs_value",
            "overall_verdict",
        ]:
            text = (reasoning.get(k) or "").strip()
            if text:
                bullets.append(ListItem(Paragraph(f"<b>{k.replace('_',' ').title()}:</b> {text}", bullet_style)))
        if bullets:
            story.append(Paragraph("Reasoning", h3))
            story.append(ListFlowable(bullets, bulletType="bullet", start="•", leftPadding=12))
            story.append(Spacer(1, 6))

        if roadmap:
            story.append(Paragraph("Implementation Roadmap", h3))
            story.append(Paragraph(roadmap.replace("\n", "<br/>"), body))
            story.append(Spacer(1, 6))

        if idx < len(ranked):
            story.append(PageBreak())

    return story


def _on_page(canvas, doc):
    canvas.saveState()
    w, h = LETTER
    footer = f"Page {doc.page}"
    fw = stringWidth(footer, "Helvetica", 9)
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.grey)
    canvas.drawString((w - fw) / 2.0, 18, footer)
    canvas.restoreState()


def main() -> None:
    ap = argparse.ArgumentParser(description="Export evaluations.json to a readable PDF report")
    ap.add_argument("--input", default="scgai/AI Challenge/output/evaluations.json", help="Path to evaluations.json")
    ap.add_argument("--output", default="scgai/AI Challenge/output/evaluations.pdf", help="PDF output path")
    ap.add_argument("--title", default="AI Challenge Evaluations", help="Report title")
    args = ap.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    if not in_path.exists():
        raise SystemExit(f"Input not found: {in_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    data: List[Dict[str, Any]] = json.load(open(in_path, encoding="utf-8"))
    if REPORTLAB_AVAILABLE:
        doc = SimpleDocTemplate(
            str(out_path),
            pagesize=LETTER,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36,
            title=args.title,
        )
        story = _build_story(data, args.title)
        doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
        print(f"Wrote PDF to {out_path}")
        return

    # Fallback: use FPDF2 if ReportLab is unavailable
    try:
        from fpdf import FPDF  # type: ignore
    except Exception:
        raise SystemExit(
            "No PDF backend available. Install one of:\n"
            " - reportlab (recommended): python -m pip install --user -r requirements-pdf.txt\n"
            " - or fallback: python -m pip install --user fpdf2"
        )

    class PDF(FPDF):
        def header(self):
            self.set_font("Arial", "B", 14)
            self.cell(0, 10, args.title, 0, 1, "L")
            self.ln(2)

        def footer(self):
            self.set_y(-15)
            self.set_font("Arial", size=9)
            self.set_text_color(128)
            self.cell(0, 10, f"Page {self.page_no()}", 0, 0, "C")

    def to_ascii(s: str) -> str:
        try:
            return s.encode("latin-1", "replace").decode("latin-1")
        except Exception:
            return s

    def stars(n: int) -> str:
        return "*" * n + "." * (5 - n)

    pdf = PDF(format="Letter")
    pdf.set_auto_page_break(auto=True, margin=15)

    # Sort by overall score desc then name
    ranked: List[Dict[str, Any]] = []
    for ev in data:
        if not isinstance(ev, dict) or ev.get("error"):
            continue
        sc = ev.get("scores") or {}
        overall = _coerce_score(sc.get("overall_verdict"))
        ev["__overall"] = overall
        ranked.append(ev)
    ranked.sort(key=lambda r: (-r.get("__overall", 0), (r.get("submission_metadata") or {}).get("name", "")))

    for idx, ev in enumerate(ranked, 1):
        meta = ev.get("submission_metadata") or {}
        name = to_ascii(meta.get("name", ""))
        email = to_ascii(meta.get("email", ""))
        sid = to_ascii(str(meta.get("submission_id", "")))
        ts = to_ascii(meta.get("timestamp_utc", ""))
        rephr = to_ascii((ev.get("rephrased_submission") or "").replace("\n", "  "))
        scores = ev.get("scores") or {}
        reasoning = ev.get("reasoning") or {}
        overall = ev.get("__overall", 0)

        pdf.add_page()
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, f"{idx}. {name}", ln=1)
        pdf.set_font("Arial", size=11)
        pdf.cell(0, 6, f"Overall: {stars(overall)} ({overall}/5)", ln=1)
        pdf.set_text_color(100)
        pdf.set_font("Arial", size=9)
        pdf.cell(0, 5, f"ID: {sid} | {email} | {ts}", ln=1)
        pdf.set_text_color(0)
        pdf.ln(2)

        if rephr:
            pdf.set_font("Arial", "B", 11)
            pdf.cell(0, 6, "Rephrased Submission", ln=1)
            pdf.set_font("Arial", size=10)
            pdf.multi_cell(0, 5, rephr)
            pdf.ln(1)

        # Scores
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 6, "Scores (1-5)", ln=1)
        pdf.set_font("Arial", size=10)
        for k in [
            "specificity",
            "strategic_alignment",
            "value_roi",
            "feasibility",
            "non_technical_usability",
            "novelty_creativity",
            "technical_complexity_vs_value",
            "overall_verdict",
        ]:
            s = _coerce_score((scores or {}).get(k))
            label = k.replace("_", " ").title()
            pdf.cell(0, 5, f"- {label}: {s}", ln=1)

        # Reasoning bullets
        pdf.ln(1)
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 6, "Reasoning", ln=1)
        pdf.set_font("Arial", size=10)
        for k in [
            "specificity",
            "strategic_alignment",
            "value_roi",
            "feasibility",
            "non_technical_usability",
            "novelty_creativity",
            "technical_complexity_vs_value",
            "overall_verdict",
        ]:
            text = to_ascii((reasoning.get(k) or "").replace("\n", "  "))
            if text:
                pdf.multi_cell(0, 5, f"• {k.replace('_',' ').title()}: {text}")

        roadmap = to_ascii((ev.get("implementation_roadmap") or "").replace("\n", "  "))
        if roadmap:
            pdf.ln(1)
            pdf.set_font("Arial", "B", 11)
            pdf.cell(0, 6, "Implementation Roadmap", ln=1)
            pdf.set_font("Arial", size=10)
            pdf.multi_cell(0, 5, roadmap)

    pdf.output(str(out_path))
    print(f"Wrote PDF to {out_path} (fpdf2 fallback)")


if __name__ == "__main__":
    main()
