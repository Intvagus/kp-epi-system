"""coverage_summary.py tested against the real December 2025 + Jan-Dec 2025
files (run through the actual load/clean pipeline), pinned to real numbers --
same convention as test_indicators.py.

Monthly and cumulative are always built and asserted separately here -- this
module never merges the two period types into one view (see
build_coverage_summary's docstring).
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


@pytest.fixture(scope="module")
def summary(district_and_uc):
    district_all, uc_all = district_and_uc
    return build_coverage_summary(district_all, uc_all)


def test_coverage_summary_status_ok(summary):
    assert summary["status"] == "ok"


def test_both_period_kinds_are_present_and_independent(summary):
    # Monthly and cumulative must both build to a full, standalone summary --
    # neither should reference or merge the other.
    assert summary["periods"]["monthly"]["status"] == "ok"
    assert summary["periods"]["cumulative"]["status"] == "ok"
    assert "month_vs_cumulative" not in summary["periods"]["monthly"]["executive"]
    assert "month_vs_cumulative" not in summary["periods"]["cumulative"]["executive"]


def test_monthly_executive_summary_is_december_2025(summary):
    exe = summary["periods"]["monthly"]["executive"]
    assert exe["current_period_id"] == "2025-12"
    assert exe["current_period_label"] == "December 2025"
    # Province total row, December 2025: FIC# 62461 / target 95554 = 65.4% -> 65.0 rounded to 1dp
    assert exe["fic_pct"] == pytest.approx(65.0, abs=0.5)
    assert exe["fic_rag"] == "warning"


def test_cumulative_executive_summary_is_jan_dec_2025(summary):
    exe = summary["periods"]["cumulative"]["executive"]
    assert exe["current_period_id"] == "2025-annual"
    assert exe["current_period_label"] == "Jan-Dec 2025 (cumulative)"
    # Cumulative FIC coverage is higher than the December-only snapshot --
    # confirms these are genuinely different, non-merged numbers.
    assert exe["fic_pct"] > summary["periods"]["monthly"]["executive"]["fic_pct"]


def test_all_json_types_are_native(summary):
    import json
    # Would previously silently stringify numpy int64 percentages (e.g. "65"
    # instead of 65.0) via json.dump's default=str fallback -- assert real
    # floats/ints survive a round-trip instead.
    payload = json.loads(json.dumps(summary, default=str))
    assert isinstance(payload["periods"]["monthly"]["executive"]["fic_pct"], float)
    assert isinstance(payload["periods"]["monthly"]["executive"]["district_compliance"]["good"], int)


def test_best_antigen_can_differ_between_monthly_and_cumulative(summary):
    # December alone: BCG leads (95%). Jan-Dec cumulative: Penta1 narrowly
    # overtakes BCG (96% vs 95%) -- genuinely different numbers, which is
    # exactly why these two views must never be merged into one.
    assert summary["periods"]["monthly"]["executive"]["best_antigen"]["antigen"] == "BCG"
    assert summary["periods"]["cumulative"]["executive"]["best_antigen"]["antigen"] == "Penta1"


def test_executive_summary_has_district_level_extremes_not_uc_level(summary):
    exe = summary["periods"]["monthly"]["executive"]
    assert "best_district" in exe and "worst_district" in exe
    assert "district_compliance" in exe
    # The old UC-level executive fields are gone -- Section 2 (uc_compliance,
    # a sibling key of "executive") is the only place UC-level detail lives.
    assert "best_uc" not in exe and "worst_uc" not in exe and "uc_compliance" not in exe
    assert exe["best_district"]["district"]
    assert exe["worst_district"]["district"]


def test_district_compliance_counts_are_over_36_real_districts(summary):
    # 36 real districts (KP Province Total excluded) all have a valid FIC
    # figure at district level (unlike UCs, no zero-target districts here).
    exe = summary["periods"]["monthly"]["executive"]
    dc = exe["district_compliance"]
    assert dc["total_with_data"] == 36
    assert dc["good"] + dc["warning"] + dc["poor"] == 36


def test_cumulative_has_its_own_full_six_sections(summary):
    cum = summary["periods"]["cumulative"]
    assert cum["uc_compliance"]["period_id"] == "2025-annual"
    assert cum["target_gap"]["period_id"] == "2025-annual"
    assert cum["dropout"]["period_id"] == "2025-annual"
    assert len(cum["antigen_analysis"]) == 9


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


def test_dropout_analysis_has_highest_and_lowest_district_lists(district_and_uc):
    district_all, uc_all = district_and_uc
    dropout = build_dropout_analysis(district_all, uc_all, "2025-12")
    assert dropout["negative_dropout_districts"] >= 0
    assert 0 < len(dropout["highest_districts"]) <= 5
    assert 0 < len(dropout["lowest_districts"]) <= 5
    # Highest-ranked district must actually have a higher (or equal)
    # dropout than the lowest-ranked one -- sanity check on sort direction.
    assert dropout["highest_districts"][0]["dropout_pct"] >= dropout["lowest_districts"][0]["dropout_pct"]


def test_dropout_lowest_excludes_negative_dropout_data_artifacts(district_and_uc):
    district_all, uc_all = district_and_uc
    dropout = build_dropout_analysis(district_all, uc_all, "2025-12")
    # A negative dropout is a data-entry error (Penta3# > Penta1#), never a
    # genuine best performer -- must never appear in the "lowest" ranking.
    assert all(d["dropout_pct"] >= 0 for d in dropout["lowest_districts"])


def test_uc_compliance_covers_wider_antigen_set_than_district(district_and_uc):
    _, uc_all = district_and_uc
    compliance = build_uc_compliance(uc_all, "2025-12")
    # UC level has OPV/PCV/Rota that District/Tehsil never has.
    assert "OPV0" in compliance["by_antigen"]
    assert "PCV1" in compliance["by_antigen"]
    assert len(compliance["top_ucs"]) == 5
    assert len(compliance["bottom_ucs"]) == 5


def test_uc_compliance_includes_opv3_and_pcv3(district_and_uc):
    # OPV3/PCV3 are real columns in the UC Wise Analysis - Coverages sheet
    # (percentage-only, no District-level equivalent) -- confirmed present
    # by direct inspection, must not be silently dropped.
    _, uc_all = district_and_uc
    compliance = build_uc_compliance(uc_all, "2025-12")
    assert "OPV3" in compliance["by_antigen"]
    assert "PCV3" in compliance["by_antigen"]
    assert compliance["by_antigen"]["OPV3"]["total_with_data"] == 1376
    assert compliance["by_antigen"]["PCV3"]["total_with_data"] == 1376


def test_uc_compliance_top_ucs_excludes_outlier_artifacts(district_and_uc):
    _, uc_all = district_and_uc
    compliance = build_uc_compliance(uc_all, "2025-12")
    # A UC above the outlier threshold (>120%) is a known data-entry artifact
    # (see clean.py's is_outlier flag), never a genuine top performer.
    assert all(r["pct"] <= 120 for r in compliance["top_ucs"])


def test_trends_reports_insufficient_history_with_only_one_monthly_file(district_and_uc):
    district_all, _ = district_and_uc
    trends = build_trends(district_all, "monthly")
    assert trends["status"] == "insufficient_history"
    assert trends["periods_available"] == 1


def test_trends_reports_insufficient_history_with_only_one_cumulative_file(district_and_uc):
    district_all, _ = district_and_uc
    trends = build_trends(district_all, "cumulative_annual")
    assert trends["status"] == "insufficient_history"
    assert trends["periods_available"] == 1
    assert trends["message"].count("file has") == 1  # singular, not "1 file(s)"


def test_every_section_has_a_short_insight_for_both_period_kinds(summary):
    for kind in ["monthly", "cumulative"]:
        period = summary["periods"][kind]
        assert period["executive"]["insight"]
        assert period["uc_compliance"]["insight"]
        assert period["antigen_insight"]
        assert period["target_gap"]["insight_by_antigen"]["FIC"]
        assert period["dropout"]["insight"]


def test_antigen_analysis_uses_vaccinated_not_covered_as_the_field_name(district_and_uc):
    district_all, _ = district_and_uc
    rows = build_antigen_analysis(district_all, "2025-12")
    assert "vaccinated" in rows[0]
    assert "covered" not in rows[0]


def test_district_to_boundary_mapping_is_exhaustive(district_and_uc):
    # Every real district (excluding the KP Province Total aggregate row)
    # must have a boundary polygon -- an unmapped district would silently
    # vanish from the map otherwise.
    district_all, _ = district_and_uc
    from src.pipeline.coverage_summary import build_district_map
    dmap = build_district_map(district_all, "2025-12")
    assert dmap["unmapped_districts"] == []


def test_district_to_boundary_names_all_exist_in_the_geojson_file():
    import json
    from pathlib import Path
    from src.pipeline.coverage_summary import DISTRICT_TO_BOUNDARY
    geojson_path = Path(__file__).resolve().parents[1] / "src" / "dashboard" / "kp_districts.geojson"
    with open(geojson_path, encoding="utf-8") as f:
        gj = json.load(f)
    boundary_names_in_file = {f["properties"]["shapeName"] for f in gj["features"]}
    assert set(DISTRICT_TO_BOUNDARY.values()) <= boundary_names_in_file


def test_district_map_kohistan_is_summed_not_averaged(district_and_uc):
    # Kohistan combines 3 real districts (Kohistan Lower, Kohistan Upper,
    # Kolai Palas Kohistan) -- confirm the combined FIC vaccinated count on
    # the map equals the sum of the three, not an average of percentages.
    district_all, _ = district_and_uc
    from src.pipeline.coverage_summary import build_district_map
    dmap = build_district_map(district_all, "2025-12")
    kohistan = dmap["features"]["Kohistan"]
    assert set(kohistan["component_districts"]) == {"Kohistan Lower", "Kohistan Upper", "Kolai Palas Kohistan"}

    rows = district_all[(district_all["period_id"] == "2025-12") &
                         (district_all["district"].isin(kohistan["component_districts"]))]
    expected_vaccinated = int(rows["fic_n"].sum())
    expected_target = int(rows["target_surviving_infants"].sum())
    assert kohistan["by_antigen"]["FIC"]["vaccinated"] == expected_vaccinated
    assert kohistan["by_antigen"]["FIC"]["target"] == expected_target
    assert kohistan["by_antigen"]["FIC"]["pct"] == pytest.approx(expected_vaccinated / expected_target * 100, abs=0.1)
