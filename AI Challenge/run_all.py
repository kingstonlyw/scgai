import argparse
import os
import subprocess
import sys
from pathlib import Path


def find_first(paths):
    for p in paths:
        if p and Path(p).exists():
            return str(Path(p))
    return None


def main() -> None:
    base = Path(__file__).parent.resolve()
    # Load .env from this folder if available so OPENAI_API_KEY is picked up
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(dotenv_path=base / ".env")
        load_dotenv()
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Run the full pipeline: Excel -> submissions -> evaluations -> meta -> front-facing")
    ap.add_argument("--excel", default=str(base / "data" / "form_data.xlsx"), help="Path to Excel input (downloaded or local)")
    ap.add_argument("--sheet", default="Sheet1", help="Sheet name or index (default: Sheet1)")
    ap.add_argument("--header-row", type=int, default=1, help="Header row (1-based)")
    ap.add_argument("--skip-llm", action="store_true", help="Skip the LLM evaluation step")
    ap.add_argument("--export-pdf", action="store_true", help="Export evaluations to a PDF report at the end")
    # Front-facing options
    ap.add_argument("--front-plus", action="store_true", help="Use enhanced front-facing builder with LLM options")
    ap.add_argument("--front-llm-title", action="store_true", help="Generate LLM titles in front-facing output (with --front-plus)")
    ap.add_argument("--front-llm-clean", action="store_true", help="Include LLM-cleaned fields in front-facing output (with --front-plus)")
    ap.add_argument("--with-keywords", action="store_true", help="Extract AI keywords for front-facing word cloud")
    # Optional fetch step (Microsoft Graph)
    ap.add_argument("--fetch-share-link", help="Fetch Excel from a Graph share link before processing")
    ap.add_argument("--fetch-user", help="Fetch from OneDrive user (userPrincipalName)")
    ap.add_argument("--fetch-path", help="Path under OneDrive/SharePoint drive root to file (with --fetch-user or site options)")
    ap.add_argument("--fetch-site-host", help="SharePoint host (e.g., contoso.sharepoint.com)")
    ap.add_argument("--fetch-site-path", help="SharePoint site path (e.g., /sites/Team)")
    args = ap.parse_args()

    excel = Path(args.excel)
    out_dir = base / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Locate scripts (prefer local copies, then parent)
    converter = find_first([
        base / "process_form_data_openpyxl.py",
        base.parent / "process_form_data_openpyxl.py",
    ])
    evaluator = find_first([
        base / "evaluate_submissions.py",
        base.parent / "evaluate_submissions.py",
    ])
    aggregator = find_first([
        base / "aggregate_meta.py",
        base.parent / "aggregate_meta.py",
    ])
    front_builder = find_first([
        base / "build_front_facing.py",
        base.parent / "build_front_facing.py",
    ])
    front_builder_plus = find_first([
        base / "build_front_facing_plus.py",
        base.parent / "build_front_facing_plus.py",
    ])
    fetcher = find_first([
        base / "fetch_form_excel.py",
        base.parent / "fetch_form_excel.py",
    ])
    exporter = find_first([
        base / "export_pdf.py",
        base.parent / "export_pdf.py",
    ])
    keyword_extractor = find_first([
        base / "extract_keywords.py",
        base.parent / "extract_keywords.py",
    ])

    if not converter:
        print("Cannot find process_form_data_openpyxl.py", file=sys.stderr)
        sys.exit(2)
    if not evaluator and not args.skip_llm:
        print("Cannot find evaluate_submissions.py (use --skip-llm to skip)", file=sys.stderr)
        sys.exit(2)
    if not aggregator:
        print("Cannot find aggregate_meta.py", file=sys.stderr)
        sys.exit(2)
    if not front_builder:
        print("Cannot find build_front_facing.py", file=sys.stderr)
        sys.exit(2)

    # Optional fetch step
    if fetcher and (
        args.fetch_share_link or (args.fetch_user and args.fetch_path) or (args.fetch_site_host and args.fetch_site_path and args.fetch_path)
    ):
        print("[0/4] Fetching Excel via Microsoft Graph …")
        fetch_cmd = [
            sys.executable,
            fetcher,
            "--dest",
            str(excel),
        ]
        if args.fetch_share_link:
            fetch_cmd += ["--share-link", args.fetch_share_link]
        elif args.fetch_user and args.fetch_path:
            fetch_cmd += ["--user", args.fetch_user, "--file-path", args.fetch_path]
        elif args.fetch_site_host and args.fetch_site_path and args.fetch_path:
            fetch_cmd += [
                "--site-host",
                args.fetch_site_host,
                "--site-path",
                args.fetch_site_path,
                "--file-path",
                args.fetch_path,
            ]
        subprocess.run(fetch_cmd, check=True)

    # Optional rename mapping
    rename = find_first([
        base / "config" / "rename.json",
        base.parent / "config" / "rename.json",
    ])

    # Step 1: Excel -> submissions.json
    submissions_path = out_dir / "submissions.json"
    cmd = [
        sys.executable,
        converter,
        "--excel",
        str(excel),
        "--sheet",
        str(args.sheet),
        "--header-row",
        str(args.header_row),
        "--date-cols",
        "Start time",
        "Completion time",
        "Last modified time",
        "--date-format",
        "%Y-%m-%dT%H:%M:%S",
        "--output",
        str(submissions_path),
        "--pretty",
        "--dropna",
    ]
    if rename:
        cmd.extend(["--rename", rename])
    print("[1/4] Building submissions.json …")
    subprocess.run(cmd, check=True)

    # Step 2: submissions -> evaluations.json (LLM)
    evaluations_path = out_dir / "evaluations.json"
    if args.skip_llm:
        print("[2/4] Skipping LLM evaluation (per flag)")
    else:
        if not os.getenv("OPENAI_API_KEY"):
            print("[2/4] ERROR: OPENAI_API_KEY not set. Create scgai/AI Challenge/.env with: \nOPENAI_API_KEY=sk-your-key", file=sys.stderr)
            sys.exit(3)
        if not evaluator:
            print("[2/4] ERROR: evaluator script not found", file=sys.stderr)
            sys.exit(3)
        print("[2/4] Running evaluations …")
        # Run in the base dir so relative paths (output/…) match
        subprocess.run([sys.executable, evaluator], check=True, cwd=str(base))
        if not evaluations_path.exists():
            print("[2/4] ERROR: evaluations.json not produced", file=sys.stderr)
            sys.exit(4)

    # Step 3: evaluations + submissions -> meta.json
    print("[3/4] Aggregating meta statistics …")
    subprocess.run([
        sys.executable,
        aggregator,
        "--evaluations",
        str(evaluations_path),
        "--submissions",
        str(submissions_path),
        "--output",
        str(out_dir / "meta.json"),
    ], check=True)

    # Step 4: Build front-facing list
    print("[4/4] Building front-facing list …")
    front_out = str(out_dir / "front_facing.json")
    if args.front_plus and front_builder_plus:
        cmd_front = [
            sys.executable,
            front_builder_plus,
            "--input", str(evaluations_path),
            "--output", front_out,
        ]
        if args.front_llm_title:
            cmd_front.append("--llm-title")
        if args.front_llm_clean:
            cmd_front += ["--llm-clean", "--submissions", str(submissions_path)]
        subprocess.run(cmd_front, check=True)
    else:
        subprocess.run([
            sys.executable,
            front_builder,
            "--input",
            str(evaluations_path),
            "--output",
            front_out,
        ], check=True)

    # Optional: AI keyword extraction
    if args.with_keywords:
        if not keyword_extractor:
            print("[extra] Keyword extractor script not found", file=sys.stderr)
        elif not evaluations_path.exists():
            print("[extra] Skipping keyword extraction (evaluations.json missing)", file=sys.stderr)
        elif args.skip_llm:
            print("[extra] Skipping keyword extraction because --skip-llm was used", file=sys.stderr)
        else:
            print("[extra] Extracting AI keywords …")
            subprocess.run([sys.executable, keyword_extractor], check=True)

    # Step 5: Currently optional: export PDF
    if args.export_pdf:
        if not exporter:
            print("[extra] Exporter script not found for PDF", file=sys.stderr)
        else:
            print("[extra] Exporting evaluations PDF …")
            subprocess.run([
                sys.executable,
                exporter,
                "--input",
                str(evaluations_path),
                "--output",
                str(out_dir / "evaluations.pdf"),
            ], check=True)

    print("Done. Outputs:")
    print(f" - {submissions_path}")
    if evaluations_path.exists():
        print(f" - {evaluations_path}")
    print(f" - {out_dir / 'meta.json'}")
    print(f" - {out_dir / 'front_facing.json'}")


if __name__ == "__main__":
    main()
