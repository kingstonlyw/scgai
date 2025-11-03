AI Challenge Pipeline

Purpose
- Convert Microsoft Forms exports (Excel) into structured JSON for intranet pages.
- Evaluate submissions via ChatGPT and aggregate meta statistics.
- Optionally fetch the Excel directly from OneDrive/SharePoint using Microsoft Graph.

Data Flow
- Excel → Submissions: `process_form_data_openpyxl.py` → `scgai/AI Challenge/output/submissions.json`
- Submissions → Evaluations: `evaluate_submissions.py` → `scgai/AI Challenge/output/evaluations.json`
- Evaluations + Submissions → Meta: `aggregate_meta.py` → `scgai/AI Challenge/output/meta.json`
- Evaluations → Front List: `build_front_facing.py` → `scgai/AI Challenge/output/front_facing.json`

Fetching Excel (Microsoft Graph)
- Install: `python -m pip install --user -r requirements-graph.txt`
- Entra ID app (admin may be required):
  - Set `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET` in `.env`.
  - Grant Application permissions: `Files.Read.All`, `Sites.Read.All` (or `Sites.Selected`) → Grant admin consent.
- Options:
  - Share link:  
    `python "scgai/AI Challenge/fetch_form_excel.py" --share-link "https://…" --dest "scgai/AI Challenge/data/form_data.xlsx"`
  - OneDrive (user + path):  
    `python "scgai/AI Challenge/fetch_form_excel.py" --user user@contoso.com --file-path "Apps/Microsoft Forms/<Form Name>/Responses.xlsx" --dest "scgai/AI Challenge/data/form_data.xlsx"`
  - SharePoint (site + path):  
    `python "scgai/AI Challenge/fetch_form_excel.py" --site-host contoso.sharepoint.com --site-path /sites/Team --file-path "Shared Documents/Forms Responses.xlsx" --dest "scgai/AI Challenge/data/form_data.xlsx"`

Run All (one command)
- Default (local Excel already present):  
  `python "scgai/AI Challenge/run_all.py"`
- Fetch first via Graph (examples):
  - Share link:  
    `python "scgai/AI Challenge/run_all.py" --fetch-share-link "https://…"`
  - OneDrive user/path:  
    `python "scgai/AI Challenge/run_all.py" --fetch-user user@contoso.com --fetch-path "Apps/Microsoft Forms/<Form Name>/Responses.xlsx"`
  - SharePoint site/path:  
    `python "scgai/AI Challenge/run_all.py" --fetch-site-host contoso.sharepoint.com --fetch-site-path /sites/Team --fetch-path "Shared Documents/Forms Responses.xlsx"`
- Skip LLM grading step: add `--skip-llm`

Secrets
- ChatGPT: `.env` with `OPENAI_API_KEY=sk-…` in this folder (gitignored).
- Graph: `.env` with `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET`.

Outputs
- `scgai/AI Challenge/output/submissions.json`
- `scgai/AI Challenge/output/evaluations.json`
- `scgai/AI Challenge/output/meta.json`
- `scgai/AI Challenge/output/front_facing.json`

PDF Export
- Install: `python -m pip install --user -r requirements-pdf.txt`
- Create a PDF from evaluations:
  - `python "scgai/AI Challenge/export_pdf.py" --input "scgai/AI Challenge/output/evaluations.json" --output "scgai/AI Challenge/output/evaluations.pdf"`
- Or include in the orchestrator:
  - `python "scgai/AI Challenge/run_all.py" --export-pdf`
