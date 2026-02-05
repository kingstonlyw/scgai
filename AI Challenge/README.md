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

## `run_all.py` Parameters

### Inputs
| Parameter | Description | Default |
|-----------|-------------|---------|
| `--excel` | Path to the Excel form file | `data/form_data.xlsx` |
| `--sheet` | Sheet name or index | `Sheet1` |
| `--header-row` | Header row number (1-based) | `1` |

### Pipeline
| Parameter | Description | Default |
|-----------|-------------|---------|
| `--skip-llm` | Skip the LLM evaluation step (no API key needed) | off |
| `--export-pdf` | Export evaluations to a PDF report | off |

### Front-Facing Output
The enhanced front-facing builder and LLM title/cleaning are **enabled by default**. Use the `--no-*` flags to disable them.

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--no-front-plus` | Do NOT use the enhanced front-facing builder | enabled |
| `--no-front-llm-title` | Do NOT generate LLM titles in front-facing output | enabled |
| `--no-front-llm-clean` | Do NOT include LLM-cleaned fields in front-facing output | enabled |
| `--with-keywords` | Extract AI keywords for word cloud | off |

### Ranking
| Parameter | Description | Default |
|-----------|-------------|---------|
| `--start-month` | Start month for ranking (`YYYY-MM`, e.g. `2025-08`) | none |

### Microsoft Graph (Optional)
Fetch the Excel file from SharePoint/OneDrive before processing.

| Parameter | Description |
|-----------|-------------|
| `--fetch-share-link` | Fetch Excel from a Graph share link |
| `--fetch-user` | OneDrive user (userPrincipalName) |
| `--fetch-path` | Path under OneDrive/SharePoint drive root |
| `--fetch-site-host` | SharePoint host (e.g. `contoso.sharepoint.com`) |
| `--fetch-site-path` | SharePoint site path (e.g. `/sites/Team`) |

### Examples
```bash
# Default run (local Excel, all features enabled)
python "scgai/AI Challenge/run_all.py"

# Custom Excel, skip LLM evaluation
python "scgai/AI Challenge/run_all.py" --excel "path/to/forms.xlsx" --skip-llm

# Full run with PDF export and keywords
python "scgai/AI Challenge/run_all.py" --export-pdf --with-keywords

# Disable LLM titles, set ranking start month
python "scgai/AI Challenge/run_all.py" --no-front-llm-title --start-month 2025-08
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
