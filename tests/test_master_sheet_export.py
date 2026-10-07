"""Regression tests for a real "Master Sheet" export variant found from a
live user upload (2026-10): a combined workbook ("Master_sheet_VPD_line_
list-2026_Wk_37.xlsx") bundling a Measles Indicator Sheet together with 4
VPD line lists (Measles, Diphtheria, Pertussis, NT) in ONE file, where
every previous export had these as separate files. Several independent
format differences from every file received before, all found by direct
inspection of the real uploaded file, not assumed:

1. The Indicator Sheet's data lives on a sheet literally named "Measles
   Indicator Sheet" (not a bare year like "2026"), with one extra blank row
   after the title shifting the header row from row 2 to row 3.
2. The province-total row is labelled "Provincial", not "Provincial Total".
3. A new district name variant, "KP Kohistan" (confirmed with the user to
   mean "Kolai Palas Kohistan"), and several districts already spelled this
   project's canonical way directly (e.g. "Tor Ghar", "Bajaur") rather than
   the older misspellings DISTRICT_NAME_CANONICAL's keys were built from.
4. The VPD line-list sheets use different names ("Measles linelist" vs
   "MSL LINE-LIST") and have no merged title row -- real headers sit on row
   1, not row 2.
5. The Pertussis sheet gained a real "Final Classification" trailing column
   that didn't exist in any previous file, landing at the same position the
   original column list reserved for "D/report sent to District".
6. The Diphtheria sheet has a trailing "Compiled by / ... / Compiled Date"
   sign-off row that isn't a real case.
7. The filename carries a single week number ("2026_Wk_37") with the year
   BEFORE the week, not a "Week <start>-<end>,<year>" range.

Uses small synthetic workbooks/dataframes built inline (not the real
uploaded file, which contains real case-level health data and was never
committed to this repo) so these tests run unconditionally.
"""
import pandas as pd
import pytest

from src.pipeline.clean import QualityLog
from src.pipeline.clean_vpd import clean_diphtheria, clean_pertussis
from src.pipeline.config import DISTRICT_TO_BOUNDARY, infer_vpd_period
from src.pipeline.indicator_sheet_vpd import (
    DISTRICT_NAME_CANONICAL, _find_header_row, _select_year_sheet, build_measles_incidence_map,
)


def test_infer_vpd_period_single_week_year_before_week():
    period = infer_vpd_period("Master_sheet_VPD_line_list-2026_Wk_37.xlsx")
    assert period.period_type == "cumulative_weekly"
    assert period.period_id == "2026-W37"
    assert period.label == "Week 37, 2026"


def test_infer_vpd_period_range_case_still_unchanged():
    period = infer_vpd_period("KP VPDs Line List Week 1-32,2026.xlsx")
    assert period.period_id == "2026-W1-32"


class _FakeCell:
    def __init__(self, value):
        self.value = value


class _FakeSheet:
    """Minimal stand-in for an openpyxl worksheet -- only what
    _find_header_row/_select_year_sheet actually call."""

    def __init__(self, grid: dict[tuple[int, int], object]):
        self.grid = grid

    def cell(self, row, column):
        return _FakeCell(self.grid.get((row, column)))


class _FakeWorkbook:
    def __init__(self, sheets: dict[str, _FakeSheet]):
        self.sheets = sheets
        self.sheetnames = list(sheets.keys())

    def __getitem__(self, name):
        return self.sheets[name]


def test_find_header_row_detects_shifted_header():
    # Row 1 = title, row 2 = blank (the newer export's extra row), row 3 =
    # real header -- must find row 3, not assume row 2.
    ws = _FakeSheet({
        (1, 1): "Measles Indicator sheet-2026",
        (3, 1): "District", (3, 2): "Total Population",
    })
    assert _find_header_row(ws) == 3


def test_select_year_sheet_falls_back_to_title_marker_when_no_bare_year_sheet():
    ws = _FakeSheet({
        (1, 1): "Measles Indicator sheet-2026",
        (3, 1): "District", (3, 2): "Total Population",
    })
    wb = _FakeWorkbook({"Measles Indicator Sheet": ws})
    year, found_ws, header_row = _select_year_sheet(wb)
    assert year == "2026"
    assert found_ws is ws
    assert header_row == 3


def test_select_year_sheet_prefers_bare_year_sheet_when_present():
    """Zero behaviour change for the original convention: a real
    year-named sheet with the historical row-2 header must still win."""
    year_ws = _FakeSheet({(2, 1): "District", (2, 2): "Total Population"})
    wb = _FakeWorkbook({"2026": year_ws})
    year, found_ws, header_row = _select_year_sheet(wb)
    assert year == "2026"
    assert found_ws is year_ws
    assert header_row == 2


def test_district_name_canonical_includes_kp_kohistan():
    assert DISTRICT_NAME_CANONICAL["KP Kohistan"] == "Kolai Palas Kohistan"


def test_measles_incidence_map_accepts_already_canonical_spellings():
    """A newer export already spells several districts this project's
    canonical way directly (e.g. "Tor Ghar", "Bajaur") instead of the older
    misspelling DISTRICT_NAME_CANONICAL's keys were built from -- these must
    not be reported as unmapped just because they aren't a dict key."""
    sheet = {"districts": [
        {"district": "Tor Ghar", "measles_incidence_per_million": 10},
        {"district": "Bajaur", "measles_incidence_per_million": 5},
        {"district": "KP Kohistan", "measles_incidence_per_million": 2},
        {"district": "Totally Unknown District", "measles_incidence_per_million": 1},
    ]}
    result = build_measles_incidence_map(sheet)
    assert result["unmapped_districts"] == ["Totally Unknown District"]
    assert set(result["features"]) == {"Tor Ghar", "Bajaur", "Kolai Palas Kohistan"}
    # Every canonical name this map can ever resolve to has a real boundary.
    assert "Tor Ghar" in DISTRICT_TO_BOUNDARY
    assert "Bajaur" in DISTRICT_TO_BOUNDARY


def _diphtheria_df(rows: list[list]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=[f"c{i}" for i in range(33)])


def test_clean_diphtheria_drops_trailing_compiled_by_footer_row():
    real_row = [1, "Khyber PakhtunKhwa", 1, "January, 2026", "Some HF", "Peshawar",
                "PAK/KP/1/2026/Diph/0001", "Name", "Father", "0000", "Village", "UC1",
                "Tehsil1", "Peshawar", 24, "Male"] + [None] * 17
    footer_row = ["Compiled by", "Name", "KHYBER PAKHTUNKHAWA PROVINCIAL USER",
                  "Designation", "Director Health Service EPI", "Compiled Date"] + [None] * 27
    df = _diphtheria_df([real_row, footer_row])
    log = QualityLog()
    cleaned = clean_diphtheria(df, "2026-W37", log)
    assert len(cleaned) == 1
    assert cleaned.iloc[0]["district"] == "Peshawar"
    flag_types = {f["flag_type"] for f in log.flags}
    assert "sheet_footer_row_dropped" in flag_types


def _pertussis_df(columns: list[str], rows: list[list]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=columns)


def test_clean_pertussis_detects_final_classification_trailing_column():
    """The newer export's Pertussis sheet has a real 'Final Classification'
    column at the same position the original column list reserved for
    'D/report sent to District' -- it must be read as classification text,
    not silently coerced to a date (which 'Laboratory Confirmed Pertussis'
    is not)."""
    columns = [f"c{i}" for i in range(30)] + ["Final Classification"]
    real_row = [1, "Khyber PakhtunKhwa", 1, "January, 2026", "Some HF", "Mohmand",
                "PAK/KP/1/2026/Pert/0001", "Name", "Father", "0000", "Village", "UC1",
                "Tehsil1", "Mohmand", 24, "Male"] + [None] * 14 + ["Laboratory Confirmed Pertussis"]
    df = _pertussis_df(columns, [real_row])
    log = QualityLog()
    cleaned = clean_pertussis(df, "2026-W37", log)
    assert "final_classification_raw" in cleaned.columns
    assert cleaned.iloc[0]["final_classification_raw"] == "Laboratory Confirmed Pertussis"
    # Must not have been coerced into a (nonsensical) date column.
    assert "report_sent_district_date" not in cleaned.columns or pd.isna(cleaned.iloc[0].get("report_sent_district_date"))


def test_clean_pertussis_old_shape_still_treats_last_column_as_a_date():
    """Zero behaviour change for the original convention: a file without a
    'Final Classification' header at that position must still treat it as
    report_sent_district_date, same as every real file received before."""
    columns = [f"c{i}" for i in range(31)]
    real_row = [1, "Khyber PakhtunKhwa", 1, "January, 2026", "Some HF", "Mohmand",
                "PAK/KP/1/2026/Pert/0001", "Name", "Father", "0000", "Village", "UC1",
                "Tehsil1", "Mohmand", 24, "Male"] + [None] * 14 + [pd.Timestamp("2026-01-15")]
    df = _pertussis_df(columns, [real_row])
    log = QualityLog()
    cleaned = clean_pertussis(df, "2026-W37", log)
    assert "final_classification_raw" not in cleaned.columns
    assert cleaned.iloc[0]["report_sent_district_date"] == pd.Timestamp("2026-01-15")
