## AI Challenge Pipeline (please see AI Challenge Midpoint Presentation.pdf for simplified workflow diagram)

## Purpose
- Convert Microsoft Forms exports (Excel) into structured JSON for intranet pages.
- Evaluate submissions via ChatGPT and aggregate meta statistics.
- Aggregate highest ranked submissions by month.

Note: the Excel file in `data/` should be populated from Microsoft Forms via a Power Automate flow.

## Data Flow
- Excel → Submissions: `process_form_data_openpyxl.py` → `scgai/AI Challenge/output/submissions.json`
- Submissions → Evaluations: `evaluate_submissions.py` → `scgai/AI Challenge/output/evaluations.json`
- Evaluations + Submissions → Meta: `aggregate_meta.py` → `scgai/AI Challenge/output/meta.json`
- Evaluations → Front List: `build_front_facing.py` → `scgai/AI Challenge/output/front_facing.json`
- Front List → Ranked Submissions: `rank_submissions.py` → `scgai/AI Challenge/output/ranked_submissions.json`

## Run All (one command)
Default (local Excel already present):  
```bash
python "scgai/AI Challenge/run_all.py"
```

## `run_all.py` options
If default is not specified, it defaults to `False` or `None`.

Inputs
- `--excel` – Path to the Excel form file (default: `data/form_data.xlsx`)
- `--sheet` – Sheet name or index (default: `Sheet1`)
- `--header-row` – Header row number (default: `1`)

Pipeline
- `--skip-llm` – Skip LLM evaluation
- `--export-pdf` – Export evaluations to PDF

Front-facing output
- `--front-plus` – Use enhanced front-facing builder
- `--front-llm-title` – Generate AI titles (requires `--front-plus`)
- `--front-llm-clean` – Include AI-cleaned text (requires `--front-plus`)
- `--with-keywords` – Extract AI keywords

Ranking
- `--start-month` – Start month for ranking (`YYYY-MM`)

Example
```bash
python "scgai/AI Challenge/run_all.py" --[parameter-name] [parameter-input]
```

## Secrets
- ChatGPT: `.env` with `OPENAI_API_KEY=sk-…` in this folder (gitignored).
- Graph: `.env` with `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET`.

## Outputs
- `scgai/AI Challenge/output/submissions.json`
- `scgai/AI Challenge/output/evaluations.json`
- `scgai/AI Challenge/output/meta.json`
- `scgai/AI Challenge/output/front_facing.json`
- `scgai/AI Challenge/output/ranked_submissions.json`


## PDF Export
- Install: `python -m pip install --user -r requirements-pdf.txt`
- Create a PDF from evaluations:
  - `python "scgai/AI Challenge/export_pdf.py" --input "scgai/AI Challenge/output/evaluations.json" --output "scgai/AI Challenge/output/evaluations.pdf"`
- Or include in the orchestrator:
  - `python "scgai/AI Challenge/run_all.py" --export-pdf`
