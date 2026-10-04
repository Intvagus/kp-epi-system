"""Read raw EPI coverage Excel files. Never modifies data/raw/."""
from pathlib import Path

import pandas as pd

from .config import COMBINED_DISTRICT_TEHSIL_SHEET, SHEET_NAMES, infer_period
from .detect import detect_workbook_type

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def find_raw_files(raw_dir: Path | None = None) -> list[Path]:
    """`raw_dir` defaults to this project's data/raw/ (the CLI/run_weekly.py
    path); the web app passes a per-job temp directory instead so concurrent
    uploads never see each other's files."""
    raw_dir = raw_dir or (PROJECT_ROOT / "data" / "raw")
    # VPD line lists (and any other non-coverage file) live in the same
    # folder but have a completely different sheet layout -- identified by
    # actual sheet-name content (see detect.py), not by filename convention.
    files = sorted(p for p in raw_dir.glob("*.xlsx") if detect_workbook_type(p).workbook_type == "coverage")
    if not files:
        raise FileNotFoundError(
            f"No coverage .xlsx files found in {raw_dir}. Drop the EPI coverage workbook there and re-run."
        )
    return files


def _resolve_sheet_name(available_sheets: list[str], expected_name: str) -> str | None:
    """Source exports have been seen with and without a trailing space on
    sheet names (e.g. 'District ' vs 'District', confirmed by a real upload
    that genuinely lacked the trailing space the original sample files had)
    -- match by normalized (stripped, case-insensitive) name and return
    whichever real sheet name is actually present, rather than requiring an
    exact match. Returns None if no sheet matches."""
    target = expected_name.strip().lower()
    for name in available_sheets:
        if name.strip().lower() == target:
            return name
    return None


def _read_sheet(path: Path, sheet_key: str, available_sheets: list[str] | None = None) -> pd.DataFrame:
    expected_name = SHEET_NAMES[sheet_key]
    if available_sheets is None:
        available_sheets = pd.ExcelFile(path, engine="openpyxl").sheet_names
    actual_name = _resolve_sheet_name(available_sheets, expected_name)
    if actual_name is None:
        raise ValueError(
            f"Sheet {expected_name!r} not found in {path.name}. "
            f"Expected sheets: {list(SHEET_NAMES.values())}. Sheets present: {available_sheets}."
        )
    df = pd.read_excel(path, sheet_name=actual_name, engine="openpyxl")
    # Excel exports pad sheets with thousands of fully-blank rows; trim them.
    df = df.dropna(how="all").reset_index(drop=True)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _find_header_blocks(header_row) -> list[list[int]]:
    """Split a row of column headers into contiguous runs of non-blank
    column positions, skipping blank/NaN spacer columns between them."""
    blocks: list[list[int]] = []
    current: list[int] = []
    for idx, val in enumerate(header_row):
        text = "" if val is None else str(val).strip()
        if text and text.lower() != "nan":
            current.append(idx)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def _load_combined_district_tehsil(path: Path, available_sheets: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A newer source export lays the District and Teshil sheets' data out as
    two blank-column-separated blocks inside one sheet (see
    config.py::COMBINED_DISTRICT_TEHSIL_SHEET) instead of two separate
    sheets -- confirmed by direct inspection of a real upload, column-for-
    column identical to the old separate sheets, just laid out side by side
    (plus a third, unused Category-rollup block after them). Splits by
    locating the blank-column gaps rather than hardcoding fixed column
    offsets, so a harmless change in spacer-column count doesn't silently
    misread the wrong columns -- and raises a clear error rather than
    guessing if the sheet's shape doesn't match what's expected."""
    actual_name = _resolve_sheet_name(available_sheets, COMBINED_DISTRICT_TEHSIL_SHEET)
    raw = pd.read_excel(path, sheet_name=actual_name, header=None, engine="openpyxl")
    header_row = raw.iloc[0]
    data = raw.iloc[1:].reset_index(drop=True)

    blocks = _find_header_blocks(header_row)
    if len(blocks) < 2:
        raise ValueError(
            f"{COMBINED_DISTRICT_TEHSIL_SHEET!r} sheet in {path.name} doesn't have the expected "
            f"blank-column-separated Tehsil/District blocks (found {len(blocks)} block(s))."
        )

    def _slice(cols: list[int]) -> pd.DataFrame:
        sub = data.iloc[:, cols].copy()
        sub.columns = [str(header_row.iloc[i]).strip() for i in cols]
        return sub.dropna(how="all").reset_index(drop=True)

    tehsil_df, district_df = _slice(blocks[0]), _slice(blocks[1])

    if "District" not in tehsil_df.columns or "Tehsil" not in tehsil_df.columns:
        raise ValueError(
            f"{COMBINED_DISTRICT_TEHSIL_SHEET!r}'s first block in {path.name} doesn't look like "
            f"Tehsil-level data (columns found: {list(tehsil_df.columns)[:5]}...)."
        )
    if "District" not in district_df.columns:
        raise ValueError(
            f"{COMBINED_DISTRICT_TEHSIL_SHEET!r}'s second block in {path.name} doesn't look like "
            f"District-level data (columns found: {list(district_df.columns)[:5]}...)."
        )
    return district_df, tehsil_df


def _load_district_and_tehsil(path: Path) -> dict:
    """District/Tehsil data comes from either the old separate-sheets layout
    or the newer combined-sheet layout -- whichever is actually present in
    this workbook (see COMBINED_DISTRICT_TEHSIL_SHEET above)."""
    available_sheets = pd.ExcelFile(path, engine="openpyxl").sheet_names
    has_district = _resolve_sheet_name(available_sheets, SHEET_NAMES["district"]) is not None
    has_tehsil = _resolve_sheet_name(available_sheets, SHEET_NAMES["tehsil"]) is not None
    if has_district and has_tehsil:
        return {
            "district": _read_sheet(path, "district", available_sheets),
            "tehsil": _read_sheet(path, "tehsil", available_sheets),
        }
    if _resolve_sheet_name(available_sheets, COMBINED_DISTRICT_TEHSIL_SHEET) is not None:
        district_df, tehsil_df = _load_combined_district_tehsil(path, available_sheets)
        return {"district": district_df, "tehsil": tehsil_df}
    raise ValueError(
        f"{path.name} has neither separate {SHEET_NAMES['district']!r}/{SHEET_NAMES['tehsil']!r} sheets "
        f"nor a {COMBINED_DISTRICT_TEHSIL_SHEET!r} sheet -- can't load District/Tehsil data."
    )


def load_workbook(path: Path) -> dict:
    """Load one raw workbook's four sheets plus its inferred reporting period."""
    period = infer_period(path.name)
    print(f"  Loading {path.name} -> period {period.period_id} ({period.label})")

    sheets = _load_district_and_tehsil(path)
    sheets["uc_coverages"] = _read_sheet(path, "uc_coverages")
    sheets["uc_difference"] = _read_sheet(path, "uc_difference")
    for key in SHEET_NAMES:
        print(f"    {key}: {len(sheets[key])} data rows")

    return {"path": path, "period": period, "sheets": sheets}


def load_all_workbooks(raw_dir: Path | None = None) -> list[dict]:
    workbooks = []
    for path in find_raw_files(raw_dir):
        workbooks.append(load_workbook(path))
    return workbooks
