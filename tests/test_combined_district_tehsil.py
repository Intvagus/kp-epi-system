"""Tests for the newer "Dist & Teshil Summary" combined-sheet Coverage
workbook layout -- confirmed via a real "Jan to Aug 2026.xlsx" upload
(2026-09) that this source system now sometimes exports District and
Tehsil data as two blank-column-separated blocks inside one sheet instead
of two separate "District "/"Teshil " sheets. See config.py's
COMBINED_DISTRICT_TEHSIL_SHEET and load.py's
_load_combined_district_tehsil for the parsing logic these tests cover.

This same upload also exposed a second, independent bug: infer_period only
recognized "Jan to Dec <year>" as cumulative, so "Jan to Aug 2026.xlsx" fell
through to the generic month-year regex and was silently misclassified as
"August 2026" monthly instead of a Jan-Aug cumulative period -- covered
below too.
"""
from pathlib import Path

import pytest

from src.pipeline.clean import QualityLog, clean_district, clean_tehsil
from src.pipeline.config import infer_period
from src.pipeline.detect import detect_workbook_type
from src.pipeline.load import load_workbook

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
COMBINED_FILE = RAW_DIR / "Jan to Aug 2026.xlsx"
NO_TRAILING_SPACE_FILE = RAW_DIR / "Jan to Aug 2026-4.xlsx"

pytestmark = pytest.mark.skipif(
    not COMBINED_FILE.exists(),
    reason="Real combined-sheet-layout Coverage file not present in this environment",
)


def test_detected_as_coverage_workbook():
    result = detect_workbook_type(COMBINED_FILE)
    assert result.workbook_type == "coverage"


def test_infer_period_reads_partial_year_cumulative_from_filename():
    period = infer_period("Jan to Aug 2026.xlsx")
    assert period.period_type == "cumulative_annual"
    assert period.period_id == "2026-cum-08"
    assert period.label == "Jan-Aug 2026 (cumulative)"


def test_infer_period_full_year_case_is_unchanged():
    """The generalization must not change the exact period_id/label the
    existing "Jan to Dec <year>" case already produced (pinned elsewhere by
    tests/test_coverage_summary.py's "2025-annual" assertions)."""
    period = infer_period("Jan to Dec 2025.xlsx")
    assert period.period_type == "cumulative_annual"
    assert period.period_id == "2025-annual"
    assert period.label == "Jan-Dec 2025 (cumulative)"


def test_infer_period_plain_month_is_unaffected():
    period = infer_period("Dec 2025 Coverage Analysis (0-11).xlsx")
    assert period.period_type == "monthly"
    assert period.period_id == "2025-12"


def test_load_workbook_splits_combined_sheet_into_district_and_tehsil():
    wb = load_workbook(COMBINED_FILE)
    district_df, tehsil_df = wb["sheets"]["district"], wb["sheets"]["tehsil"]

    # 36 real districts + 1 province-total row (mislabeled "Tor Ghar") + 1
    # junk "\N" export row -- same shape as the old separate-sheet layout.
    assert len(district_df) == 38
    assert len(tehsil_df) == 142

    assert list(district_df.columns[:3]) == ["S No", "District", "Target for BCG"]
    assert "Total UCs" in district_df.columns
    assert list(tehsil_df.columns[:3]) == ["District", "Tehsil", "Tehsil Code"]
    assert "Total UCs" in tehsil_df.columns

    assert "Abbottabad" in set(district_df["District"])
    assert "Abbottabad" in set(tehsil_df["District"])


def test_load_workbook_uc_sheets_unaffected_by_combined_layout():
    wb = load_workbook(COMBINED_FILE)
    assert len(wb["sheets"]["uc_coverages"]) > 0
    assert len(wb["sheets"]["uc_difference"]) > 0


def test_clean_district_and_tehsil_run_without_error_on_combined_layout():
    """The split-out district_df/tehsil_df must be drop-in compatible with
    the existing clean_district/clean_tehsil functions -- same column names
    and shapes as the old separate-sheet layout, verified end-to-end."""
    wb = load_workbook(COMBINED_FILE)
    log = QualityLog()
    period_id = wb["period"].period_id

    district = clean_district(wb["sheets"]["district"], period_id, log)
    tehsil = clean_tehsil(wb["sheets"]["tehsil"], period_id, log)

    assert len(district) == 38
    assert district["is_province_total"].sum() == 1
    assert len(tehsil) <= 142  # junk rows excluded
    assert "bcg_pct_reported" in district.columns
    assert "bcg_pct_reported" in tehsil.columns


@pytest.mark.skipif(
    not NO_TRAILING_SPACE_FILE.exists(),
    reason="Real no-trailing-space-sheet-name Coverage file not present in this environment",
)
class TestNoTrailingSpaceSheetNames:
    """A third real-world Coverage export variant (2026-10): separate
    "District"/"Teshil" sheets like the original layout, but WITHOUT the
    trailing space the original sample files had on those exact sheet
    names -- config.py's SHEET_NAMES hardcodes 'District '/'Teshil ' (with
    the trailing space), and _read_sheet() used to require an exact sheet
    name match, so this file failed with "Sheet 'District ' not found"
    even though detection correctly recognized it as a Coverage workbook.
    Fixed by resolving the actual sheet name via a normalized
    (stripped, case-insensitive) match (load.py::_resolve_sheet_name) rather
    than an exact string match, used uniformly for every sheet lookup."""

    def test_detected_as_coverage_workbook(self):
        result = detect_workbook_type(NO_TRAILING_SPACE_FILE)
        assert result.workbook_type == "coverage"

    def test_load_workbook_reads_district_and_tehsil_sheets(self):
        wb = load_workbook(NO_TRAILING_SPACE_FILE)
        assert len(wb["sheets"]["district"]) == 37
        assert len(wb["sheets"]["tehsil"]) == 139
        assert "Abbottabad" in set(wb["sheets"]["district"]["District"])

    def test_load_workbook_uc_sheets_also_read_correctly(self):
        wb = load_workbook(NO_TRAILING_SPACE_FILE)
        assert len(wb["sheets"]["uc_coverages"]) > 0
        assert len(wb["sheets"]["uc_difference"]) > 0

    def test_clean_district_and_tehsil_run_without_error(self):
        wb = load_workbook(NO_TRAILING_SPACE_FILE)
        log = QualityLog()
        period_id = wb["period"].period_id
        district = clean_district(wb["sheets"]["district"], period_id, log)
        tehsil = clean_tehsil(wb["sheets"]["tehsil"], period_id, log)
        assert len(district) == 37
        assert district["is_province_total"].sum() == 1
        assert len(tehsil) > 0
