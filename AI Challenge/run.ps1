Param(
  [string]$Excel = "data/form_data.xlsx",
  [string]$Sheet = "Sheet1",
  [int]$HeaderRow = 1,
  [string]$Output = "output/data.json"
)

$ErrorActionPreference = "Stop"

if (Test-Path ".venv/Scripts/Activate.ps1") {
  . .venv/Scripts/Activate.ps1
}

python process_form_data.py --excel $Excel --sheet $Sheet --header-row $HeaderRow --output $Output --pretty --dropna
