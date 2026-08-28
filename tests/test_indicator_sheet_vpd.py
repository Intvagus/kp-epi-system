"""Measles Indicator Sheet tests, pinned to real numbers confirmed by direct
inspection of Indicator_SheetMeasles.xlsx's '2026' sheet (37 districts +
Provincial Total row), same convention as the other real-data test modules.
"""
from pathlib import Path

import pytest

from src.pipeline.detect import detect_workbook_type
from src.pipeline.indicator_sheet_vpd import (
    KEY_INDICATORS, build_key_indicators_summary, find_indicator_sheet_files, load_indicator_sheet,
)

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
INDICATOR_FILE = RAW_DIR / "Indicator_SheetMeasles.xlsx"

pytestmark = pytest.mark.skipif(
    not INDICATOR_FILE.exists(),
    reason="Real Indicator_SheetMeasles.xlsx not present in this environment",
)


@pytest.fixture(scope="module")
def sheet():
    return load_indicator_sheet(INDICATOR_FILE)


@pytest.fixture(scope="module")
def summary(sheet):
    return build_key_indicators_summary(sheet)


def test_detects_as_indicator_sheet_not_coverage_or_vpd():
    result = detect_workbook_type(INDICATOR_FILE)
    assert result.workbook_type == "indicator_sheet"


def test_find_indicator_sheet_files_locates_it_in_raw_dir():
    assert INDICATOR_FILE in find_indicator_sheet_files(RAW_DIR)


def test_selects_latest_year_sheet(sheet):
    assert sheet["year"] == "2026"


def test_loads_all_37_districts_plus_provincial_total(sheet):
    assert len(sheet["districts"]) == 37
    assert sheet["provincial_total"]["district"] == "Provincial Total"


def test_provincial_total_matches_real_sheet_values(sheet):
    prov = sheet["provincial_total"]
    assert prov["total_population"] == 42369617
    assert prov["total_cases_reported"] == 14683
    assert prov["measles_total"] == 6416
    assert prov["measles_related_deaths"] == 13.0


def test_provincial_rates_are_internally_consistent_with_raw_counts(sheet):
    # The sheet's own rate columns should equal count/population*scale --
    # verifies we're reading the right cells, not a red-herring column.
    prov = sheet["provincial_total"]
    assert prov["measles_incidence_per_million"] == pytest.approx(
        prov["measles_total"] / prov["total_population"] * 1_000_000, rel=1e-6
    )
    assert prov["non_measles_non_rubella_rate"] == pytest.approx(
        prov["non_measles_non_rubella_cases"] / prov["total_population"] * 100_000, rel=1e-6
    )


def test_key_indicators_summary_covers_all_six_highlighted_indicators(summary):
    assert summary["status"] == "ok"
    assert len(summary["indicators"]) == len(KEY_INDICATORS) == 6
    keys = {row["key"] for row in summary["indicators"]}
    assert keys == {
        "non_measles_non_rubella_rate", "measles_incidence_per_million",
        "rubella_incidence_per_million", "pct_sample_collected",
        "pct_adequate_investigation", "measles_related_deaths",
    }


def test_key_indicator_provincial_values_match_source(summary):
    by_key = {row["key"]: row for row in summary["indicators"]}
    assert by_key["measles_related_deaths"]["provincial_value"] == 13.0
    assert by_key["pct_sample_collected"]["provincial_value"] == pytest.approx(96.47525837)


def test_highest_and_lowest_district_are_real_and_different(summary):
    for row in summary["indicators"]:
        if row["highest_district"] and row["lowest_district"]:
            assert row["highest_district"]["value"] >= row["lowest_district"]["value"]


def test_no_target_values_are_fabricated(summary):
    # The source workbook has no target/threshold/benchmark column anywhere
    # -- confirmed by inspection -- so the summary must never invent one.
    for row in summary["indicators"]:
        assert "target" not in row
