import argparse
import json
import os
from pathlib import Path
from typing import Dict, List

import pandas as pd

# THIS FILE IS NOT WORKING YET, NEED MORE ACCESS TO USE

def parse_filter_eq(values: List[str]) -> Dict[str, str]:
    filters = {}
    for v in values or []:
        if "=" not in v:
            raise ValueError(f"Invalid --filter-eq '{v}'. Use Column=Value")
        key, val = v.split("=", 1)
        filters[key.strip()] = val.strip()
    return filters


def ensure_parent_dir(path: Path) -> None:
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)


def load_rename_mapping(path: str | None) -> Dict[str, str]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        mapping = json.load(f)
    if not isinstance(mapping, dict):
        raise ValueError("--rename must be a JSON object mapping source->target column names")
    return mapping


def coerce_and_format_dates(df: pd.DataFrame, date_cols: List[str], date_format: str) -> pd.DataFrame:
    if not date_cols:
        return df
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
            df[col] = df[col].dt.strftime(date_format)
    return df


def apply_filters(df: pd.DataFrame, filters: Dict[str, str]) -> pd.DataFrame:
    if not filters:
        return df
    mask = pd.Series([True] * len(df))
    for col, val in filters.items():
        if col not in df.columns:
            # If the column is missing, filter yields no rows
            mask &= False
        else:
            # Convert both sides to string for robust matching
            mask &= (df[col].astype(str) == str(val))
    return df[mask]


def trim_str_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()
    return df


def main():
    parser = argparse.ArgumentParser(description="Convert Excel form data to structured JSON")
    parser.add_argument("--excel", required=True, help="Path to the input .xlsx file")
    parser.add_argument("--sheet", default=0, help="Sheet name or index (default: 0)")
    parser.add_argument(
        "--header-row",
        type=int,
        default=1,
        help="1-based header row number containing column names (default: 1)",
    )
    parser.add_argument(
        "--rename",
        help="Path to JSON file mapping source column names to desired output names",
    )
    parser.add_argument(
        "--date-cols",
        nargs="*",
        default=[],
        help="Column names to parse and format as dates",
    )
    parser.add_argument(
        "--date-format",
        default="%Y-%m-%d",
        help="Python strftime format for dates (default: %Y-%m-%d)",
    )
    parser.add_argument(
        "--filter-eq",
        nargs="*",
        default=[],
        help="Equality filters like Status=Active (repeatable)",
    )
    parser.add_argument(
        "--dropna",
        action="store_true",
        help="Drop rows that are entirely empty",
    )
    parser.add_argument(
        "--output",
        default="output/data.json",
        help="Path to write JSON output (default: output/data.json)",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON with indentation")

    args = parser.parse_args()

    excel_path = Path(args.excel)
    if not excel_path.exists():
        raise SystemExit(f"Excel file not found: {excel_path}")

    # Convert header row from 1-based to 0-based index for pandas
    header_idx = max(args.header_row - 1, 0)

    sheet = args.sheet
    try:
        sheet = int(sheet)
    except (TypeError, ValueError):
        # keep as string if not an int
        pass

    try:
        df = pd.read_excel(excel_path, sheet_name=sheet, header=header_idx, engine="openpyxl")
    except Exception as e:
        raise SystemExit(f"Failed to read Excel: {e}")

    # Normalize and clean
    df = trim_str_columns(df)
    if args.dropna:
        df = df.dropna(how="all")

    # Column renames
    rename_map = load_rename_mapping(args.rename)
    if rename_map:
        # Only rename columns that exist to avoid surprises
        available = {k: v for k, v in rename_map.items() if k in df.columns}
        df = df.rename(columns=available)

    # Date handling
    df = coerce_and_format_dates(df, args.date_cols, args.date_format)

    # Filters
    filters = parse_filter_eq(args.filter_eq)
    df = apply_filters(df, filters)

    # Ensure output dir
    out_path = Path(args.output)
    ensure_parent_dir(out_path)

    # Emit JSON
    records = df.to_dict(orient="records")
    indent = 2 if args.pretty else None
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=indent)

    print(f"Wrote {len(records)} records to {out_path}")


if __name__ == "__main__":
    main()
