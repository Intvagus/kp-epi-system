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

    # 37 real districts (including a real "Tor Ghar" row -- this export no
    # longer mislabels the province total that way, see
    # test_clean_district_and_tehsil_run_without_error_on_combined_layout
    # below) + 1 province-total row (labelled "\N" in this export, not
    # "Tor Ghar") -- same row count as the old separate-sheet layout, just a
    # different real/mislabeled split than that older convention.
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
    # The real province-total row in this export is labelled "\N", not
    # "Tor Ghar" -- "Tor Ghar" here is real district data and must survive
    # as its own row (see test_combined_layout_tor_ghar_kept_as_real_district
    # below for the full regression test).
    assert district.loc[district["is_province_total"], "district"].iloc[0] == "KP Province Total"
    assert "Tor Ghar" in set(district["district"])
    assert len(tehsil) <= 142  # junk rows excluded
    assert "bcg_pct_reported" in district.columns
    assert "bcg_pct_reported" in tehsil.columns


def test_combined_layout_tor_ghar_kept_as_real_district():
    """Regression test for the same 2026-10 Tor Ghar bug covered in
    TestNoTrailingSpaceSheetNames, on this file's own district layout: this
    export's real province-wide total is under the literal "\\N" label
    (an export artifact, same convention as the junk Tehsil rows), while
    "Tor Ghar" itself is real, plausible single-district data (target
    ~3,990, the same order of magnitude as this province's other small
    districts) that must be kept, not swallowed into "KP Province Total"."""
    wb = load_workbook(COMBINED_FILE)
    log = QualityLog()
    district = clean_district(wb["sheets"]["district"], wb["period"].period_id, log)

    tor_ghar = district[district["district"] == "Tor Ghar"]
    assert len(tor_ghar) == 1
    assert tor_ghar.iloc[0]["is_province_total"] == False
    assert tor_ghar.iloc[0]["target_surviving_infants"] == 3990

    province_total = district[district["is_province_total"]]
    assert len(province_total) == 1
    assert province_total.iloc[0]["target_surviving_infants"] == 774597

    flag_types = {f["flag_type"] for f in log.flags}
    assert "tor_ghar_kept_as_real_district" in flag_types
    assert "province_total_mislabeled" in flag_types


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
        # This file's "Tor Ghar" row is real, plausible single-district data
        # (target ~4,212, in the same range as the province's other small
        # districts), not the legacy mislabeled province-total row -- see
        # test_tor_ghar_real_district_not_mislabeled_as_province_total below
        # and CLAUDE.md's "found and fixed" note for the full story. This file
        # has no province-total row at all (neither a real one nor a
        # mislabeled one), so build_executive_summary()'s computed-fallback
        # path (see test_coverage_summary_no_province_row.py) is what
        # produces this period's province-wide KPIs.
        assert district["is_province_total"].sum() == 0
        assert len(tehsil) > 0

    def test_tor_ghar_real_district_not_mislabeled_as_province_total(self):
        """Regression test for a real bug found 2026-10 from an actual
        deployed-app upload: this exact file's "Tor Ghar" row was being
        unconditionally treated as the legacy mislabeled province-total row
        (the convention confirmed for every earlier file this project
        received), which silently (a) excluded the real Tor Ghar district
        from every district table/ranking/map, and (b) replaced every
        province-wide KPI on the dashboard with Tor Ghar's own tiny numbers
        (e.g. "Target Population: 3,990" instead of the real ~774,597)
        -- confirmed against a user-generated report screenshot. Fixed with a
        magnitude check (clean.py's PROVINCE_TOTAL_MIN_SHARE_OF_OTHERS):
        a candidate-labelled row is only treated as the province total if its
        own target is close to the summed target of every other district."""
        wb = load_workbook(NO_TRAILING_SPACE_FILE)
        log = QualityLog()
        district = clean_district(wb["sheets"]["district"], wb["period"].period_id, log)
        tor_ghar = district[district["district"] == "Tor Ghar"]
        assert len(tor_ghar) == 1
        assert tor_ghar.iloc[0]["is_province_total"] == False
        assert tor_ghar.iloc[0]["target_surviving_infants"] == 3990
        assert "KP Province Total" not in set(district["district"])
        flag_types = {f["flag_type"] for f in log.flags}
        assert "tor_ghar_kept_as_real_district" in flag_types
        assert "province_total_mislabeled" not in flag_types
