"""Read raw VPD (measles-rubella / diphtheria / NNT / pertussis) line lists.

Never modifies data/raw/. Each sheet has a merged title on row 1 and real
headers on row 2 (data from row 3) -- confirmed against
'KP VPDs Line List Week 1-32,2026.xlsx'.
"""
from pathlib import Path

import pandas as pd

from .config import VPD_HEADER_ROW, VPD_SHEET_NAMES
from .detect import detect_workbook_type
from .sheet_utils import resolve_sheet_name

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def find_vpd_files(raw_dir: Path | None = None) -> list[Path]:
    """VPD workbooks are identified by actual sheet-name content (see
    detect.py), not filename -- a real upload won't reliably be named the way
    this project's own sample file happens to be. `raw_dir` defaults to this
    project's data/raw/; the web app passes a per-job temp directory."""
    raw_dir = raw_dir or (PROJECT_ROOT / "data" / "raw")
    return sorted(p for p in raw_dir.glob("*.xlsx") if detect_workbook_type(p).workbook_type == "vpd")


def _read_sheet(path: Path, expected_name: str, available_sheets: list[str]) -> pd.DataFrame:
    # Matched by normalized (stripped, case-insensitive) name, not an exact
    # string -- same reasoning as src/pipeline/load.py's Coverage sheets:
    # these sheet names are long and irregular ("Pertusis line-list", a
    # trailing space on "DIPHTHERIA LINE-LIST "), so small naming drift
    # between source exports is a real, already-seen risk, not hypothetical.
    actual_name = resolve_sheet_name(available_sheets, expected_name)
    if actual_name is None:
        raise ValueError(
            f"Sheet {expected_name!r} not found in {path.name}. "
            f"Expected sheets: {list(VPD_SHEET_NAMES.values())}. Sheets present: {available_sheets}."
        )
    df = pd.read_excel(path, sheet_name=actual_name, header=VPD_HEADER_ROW - 1, engine="openpyxl")
    df = df.dropna(how="all").reset_index(drop=True)
    df.columns = [str(c).strip() if not str(c).startswith("Unnamed") else None for c in df.columns]
    return df


def load_vpd_workbook(path: Path) -> dict:
    print(f"  Loading {path.name} (VPD line lists)...")
    available_sheets = pd.ExcelFile(path, engine="openpyxl").sheet_names
    sheets = {}
    for key, sheet_name in VPD_SHEET_NAMES.items():
        sheets[key] = _read_sheet(path, sheet_name, available_sheets)
        print(f"    {sheet_name.strip()}: {len(sheets[key])} case rows")
    return {"path": path, "sheets": sheets}
