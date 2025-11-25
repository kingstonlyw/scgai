#!/usr/bin/env bash
set -euo pipefail

EXCEL=${1:-data/form_data.xlsx}
SHEET=${2:-Sheet1}
HEADER_ROW=${3:-1}
OUTPUT=${4:-output/data.json}

# Prefer pandas script if pandas is installed; else fallback to openpyxl-only
if python - <<'PY' 2>/dev/null; then
import importlib, sys
sys.exit(0 if importlib.util.find_spec('pandas') else 1)
PY
then
  echo "Using pandas pipeline"
  python process_form_data.py --excel "$EXCEL" --sheet "$SHEET" --header-row "$HEADER_ROW" --output "$OUTPUT" --pretty --dropna
else
  echo "Using openpyxl-only pipeline"
  python process_form_data_openpyxl.py --excel "$EXCEL" --sheet "$SHEET" --header-row "$HEADER_ROW" --rename config/rename.json --date-cols "Start time" "Completion time" "Last modified time" --date-format "%Y-%m-%dT%H:%M:%S" --output "$OUTPUT" --pretty --dropna
fi

