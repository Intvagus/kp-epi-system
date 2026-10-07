"""Read raw VPD (measles-rubella / diphtheria / NNT / pertussis) line lists.

Never modifies data/raw/. The original convention: each sheet has a merged
title on row 1 and real headers on row 2 (data from row 3) -- confirmed
against 'KP VPDs Line List Week 1-32,2026.xlsx'. A newer "Master Sheet"
export (2026-10, see indicator_sheet_vpd.py) has no merged title row at all
-- real headers sit on row 1, data from row 2 -- so the header row is
detected per sheet (_detect_header_row) rather than assumed fixed.
"""
from pathlib import Path

import openpyxl
import pandas as pd

from .config import VPD_HEADER_ROW_CANDIDATES, VPD_SHEET_NAME_ALIASES, VPD_SHEET_NAMES
from .sheet_utils import resolve_sheet_name

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# First column header text that marks a real header row, across every known
# sheet-name variant ("Sr #" for MSL/Diphtheria/Pertussis, "S #" for NNT).
_HEADER_ROW_FIRST_CELL_MARKERS = {"sr #", "sr#", "s #", "s#"}


def find_vpd_files(raw_dir: Path | None = None) -> list[Path]:
    """VPD workbooks are identified by actual sheet-name content, not
    filename -- a real upload won't reliably be named the way this project's
    own sample file happens to be. Checked independently of
    detect.py::detect_workbook_type's single per-file label, since a
    workbook can genuinely carry VPD line lists alongside another recognized
    domain in the same file (e.g. the 2026-10 "Master Sheet" export, which
    bundles line lists with a Measles Indicator Sheet) -- relying on the one
    label alone would silently drop the line-list data in that case.
    `raw_dir` defaults to this project's data/raw/; the web app passes a
    per-job temp directory."""
    raw_dir = raw_dir or (PROJECT_ROOT / "data" / "raw")
    return sorted(p for p in raw_dir.glob("*.xlsx") if has_vpd_sheets(p))


def has_vpd_sheets(path: Path) -> bool:
    """True if every one of the 4 VPD diseases has a matching sheet in this
    workbook (any known name alias), regardless of what detect_workbook_type
    classifies the file as overall."""
    try:
        available = pd.ExcelFile(path, engine="openpyxl").sheet_names
    except Exception:
        return False
    for aliases in VPD_SHEET_NAME_ALIASES.values():
        if not any(resolve_sheet_name(available, alias) for alias in aliases):
            return False
    return True


def _detect_header_row(path: Path, sheet_name: str) -> int:
    """Which row holds the real column headers -- checked per sheet rather
    than assumed, since a newer export has no merged title row (headers on
    row 1) while the original convention does (headers on row 2)."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet_name]
    for row in VPD_HEADER_ROW_CANDIDATES:
        value = str(ws.cell(row=row, column=1).value or "").strip().lower()
        if value in _HEADER_ROW_FIRST_CELL_MARKERS:
            return row
    return VPD_HEADER_ROW_CANDIDATES[0]  # fall back to the legacy default


def _read_sheet(path: Path, key: str, available_sheets: list[str]) -> pd.DataFrame:
    # Matched by normalized (stripped, case-insensitive) name against every
    # known alias for this disease, not one exact string -- a newer export
    # (2026-10) uses sheet names that aren't just whitespace/case drift from
    # the original ("Measles linelist" vs "MSL LINE-LIST"), on top of the
    # same irregular-naming risk resolve_sheet_name already handles within
    # one convention ("Pertusis line-list", a trailing space on
    # "DIPHTHERIA LINE-LIST ").
    actual_name = None
    for alias in VPD_SHEET_NAME_ALIASES[key]:
        actual_name = resolve_sheet_name(available_sheets, alias)
        if actual_name is not None:
            break
    if actual_name is None:
        raise ValueError(
            f"No sheet for {key!r} found in {path.name}. "
            f"Expected one of: {VPD_SHEET_NAME_ALIASES[key]}. Sheets present: {available_sheets}."
        )
    header_row = _detect_header_row(path, actual_name)
    df = pd.read_excel(path, sheet_name=actual_name, header=header_row - 1, engine="openpyxl")
    df = df.dropna(how="all").reset_index(drop=True)
    df.columns = [str(c).strip() if not str(c).startswith("Unnamed") else None for c in df.columns]
    return df


def load_vpd_workbook(path: Path) -> dict:
    print(f"  Loading {path.name} (VPD line lists)...")
    available_sheets = pd.ExcelFile(path, engine="openpyxl").sheet_names
    sheets = {}
    for key in VPD_SHEET_NAMES:
        sheets[key] = _read_sheet(path, key, available_sheets)
        print(f"    {key}: {len(sheets[key])} case rows")
    return {"path": path, "sheets": sheets}
