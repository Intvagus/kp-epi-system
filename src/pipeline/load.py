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


def _load_combined_district_tehsil(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
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
    raw = pd.read_excel(path, sheet_name=COMBINED_DISTRICT_TEHSIL_SHEET, header=None, engine="openpyxl")
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
    sheet_names = {s.strip() for s in pd.ExcelFile(path, engine="openpyxl").sheet_names}
    if SHEET_NAMES["district"].strip() in sheet_names and SHEET_NAMES["tehsil"].strip() in sheet_names:
        return {"district": _read_sheet(path, "district"), "tehsil": _read_sheet(path, "tehsil")}
    if COMBINED_DISTRICT_TEHSIL_SHEET in sheet_names:
        district_df, tehsil_df = _load_combined_district_tehsil(path)
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
