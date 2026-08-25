"""coverage_summary.py tested against the real December 2025 + Jan-Dec 2025
files (run through the actual load/clean pipeline), pinned to real numbers --
same convention as test_indicators.py.
"""
from pathlib import Path

import pytest

from src.pipeline.clean import QualityLog, clean_district, clean_uc
from src.pipeline.coverage_summary import (
    build_antigen_analysis,
    build_coverage_summary,
    build_dropout_analysis,
    build_target_gap,
    build_trends,
    build_uc_compliance,
)
from src.pipeline.load import load_workbook

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
DEC_FILE = RAW_DIR / "Dec 2025 Coverage Analysis (0-11).xlsx"
ANNUAL_FILE = RAW_DIR / "Jan to Dec 2025.xlsx"

pytestmark = pytest.mark.skipif(
    not (DEC_FILE.exists() and ANNUAL_FILE.exists()),
    reason="Real raw Excel files not present in this environment",
)


@pytest.fixture(scope="module")
def district_and_uc():
    import pandas as pd

    log = QualityLog()
    district_frames, uc_frames = [], []
    for path in [DEC_FILE, ANNUAL_FILE]:
        wb = load_workbook(path)
        period = wb["period"]
        d = clean_district(wb["sheets"]["district"], period.period_id, log)
        d["period_type"], d["period_label"] = period.period_type, period.label
        district_frames.append(d)
        u = clean_uc(wb["sheets"]["uc_coverages"], wb["sheets"]["uc_difference"], period.period_id, log)
        u["period_type"], u["period_label"] = period.period_type, period.label
        uc_frames.append(u)
    return pd.concat(district_frames, ignore_index=True), pd.concat(uc_frames, ignore_index=True)


def test_coverage_summary_status_ok(district_and_uc):
    district_all, uc_all = district_and_uc
    summary = build_coverage_summary(district_all, uc_all)
    assert summary["status"] == "ok"


def test_executive_summary_picks_december_as_current_period(district_and_uc):
    district_all, uc_all = district_and_uc
    summary = build_coverage_summary(district_all, uc_all)
    exe = summary["executive"]
    assert exe["current_period_id"] == "2025-12"
    # Province total row, December 2025: FIC# 62461 / target 95554 = 65.4% -> 65.0 rounded to 1dp
    assert exe["fic_pct"] == pytest.approx(65.0, abs=0.5)
    assert exe["fic_rag"] == "warning"


def test_executive_summary_all_json_types_are_native(district_and_uc):
    import json
    district_all, uc_all = district_and_uc
    summary = build_coverage_summary(district_all, uc_all)
    # Would previously silently stringify numpy int64 percentages (e.g. "65"
    # instead of 65.0) via json.dump's default=str fallback -- assert real
    # floats/ints survive a round-trip instead.
    payload = json.loads(json.dumps(summary, default=str))
    assert isinstance(payload["executive"]["fic_pct"], float)
    assert isinstance(payload["executive"]["uc_compliance"]["good"], int)


def test_best_antigen_is_bcg_december_2025(district_and_uc):
    district_all, uc_all = district_and_uc
    summary = build_coverage_summary(district_all, uc_all)
    assert summary["executive"]["best_antigen"]["antigen"] == "BCG"


def test_month_vs_cumulative_present_when_both_period_types_exist(district_and_uc):
    district_all, uc_all = district_and_uc
    summary = build_coverage_summary(district_all, uc_all)
    mvc = summary["executive"]["month_vs_cumulative"]
    assert mvc is not None
    assert mvc["monthly_label"] == "December 2025"
    assert mvc["cumulative_label"] == "Jan-Dec 2025 (cumulative)"


def test_antigen_analysis_covers_all_nine_district_antigens(district_and_uc):
    district_all, _ = district_and_uc
    rows = build_antigen_analysis(district_all, "2025-12")
    assert {r["antigen"] for r in rows} == {
        "BCG", "Penta1", "Penta2", "Penta3", "IPV1", "IPV2", "MR1", "TCV", "FIC",
    }
    # Sorted descending by pct -- BCG (95%) should lead, FIC (65%) should trail.
    assert rows[0]["antigen"] == "BCG"
    assert rows[-1]["antigen"] == "FIC"


def test_target_gap_has_no_opv_pcv_rota_since_no_target_exists_at_district_level(district_and_uc):
    district_all, _ = district_and_uc
    gap = build_target_gap(district_all, "2025-12")
    assert set(gap["by_antigen"].keys()) == {
        "BCG", "Penta1", "Penta2", "Penta3", "IPV1", "IPV2", "MR1", "TCV", "FIC",
    }


def test_dropout_analysis_formula_is_penta1_to_penta3_only(district_and_uc):
    district_all, uc_all = district_and_uc
    dropout = build_dropout_analysis(district_all, uc_all, "2025-12")
    assert "Penta1" in dropout["formula"] and "Penta3" in dropout["formula"]
    assert dropout["negative_dropout_districts"] >= 0
    assert len(dropout["worst_districts"]) > 0


def test_uc_compliance_covers_wider_antigen_set_than_district(district_and_uc):
    _, uc_all = district_and_uc
    compliance = build_uc_compliance(uc_all, "2025-12")
    # UC level has OPV/PCV/Rota that District/Tehsil never has.
    assert "OPV0" in compliance["by_antigen"]
    assert "PCV1" in compliance["by_antigen"]
    assert len(compliance["top_ucs"]) == 15
    assert len(compliance["bottom_ucs"]) == 15


def test_trends_reports_insufficient_history_with_only_one_monthly_file(district_and_uc):
    district_all, _ = district_and_uc
    trends = build_trends(district_all)
    assert trends["status"] == "insufficient_history"
    assert trends["monthly_periods_available"] == 1
