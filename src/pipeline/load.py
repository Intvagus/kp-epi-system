"""Read raw EPI coverage Excel files. Never modifies data/raw/."""
from pathlib import Path

import pandas as pd

from .config import SHEET_NAMES, infer_period

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def find_raw_files(raw_dir: Path | None = None) -> list[Path]:
    """`raw_dir` defaults to this project's data/raw/ (the CLI/run_weekly.py
    path); the web app passes a per-job temp directory instead so concurrent
    uploads never see each other's files."""
    raw_dir = raw_dir or (PROJECT_ROOT / "data" / "raw")
    # VPD line lists live in the same folder but have a completely different
    # sheet layout (see load_vpd.py) -- excluded here by filename so this
    # loader doesn't try to read them as a coverage workbook.
    files = sorted(p for p in raw_dir.glob("*.xlsx") if "vpd" not in p.name.lower())
    if not files:
        raise FileNotFoundError(
            f"No coverage .xlsx files found in {raw_dir}. Drop the EPI coverage workbook(s) there and re-run."
        )
    return files


def _read_sheet(path: Path, sheet_key: str) -> pd.DataFrame:
    sheet_name = SHEET_NAMES[sheet_key]
    try:
        df = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
    except ValueError as e:
        raise ValueError(
            f"Sheet {sheet_name!r} not found in {path.name}. "
            f"Expected sheets: {list(SHEET_NAMES.values())}. Original error: {e}"
        ) from e
    # Excel exports pad sheets with thousands of fully-blank rows; trim them.
    df = df.dropna(how="all").reset_index(drop=True)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def load_workbook(path: Path) -> dict:
    """Load one raw workbook's four sheets plus its inferred reporting period."""
    period = infer_period(path.name)
    print(f"  Loading {path.name} -> period {period.period_id} ({period.label})")

    sheets = {}
    for key in SHEET_NAMES:
        sheets[key] = _read_sheet(path, key)
        print(f"    {SHEET_NAMES[key].strip()}: {len(sheets[key])} data rows")

    return {"path": path, "period": period, "sheets": sheets}


def load_all_workbooks(raw_dir: Path | None = None) -> list[dict]:
    workbooks = []
    for path in find_raw_files(raw_dir):
        workbooks.append(load_workbook(path))
    return workbooks
