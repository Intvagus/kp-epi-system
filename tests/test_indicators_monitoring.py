"""Monitoring domain indicator tests, pinned to real numbers confirmed by
direct inspection of RCA_Report_2.xls / Supervisory_Checklist_Report.xls
(both real field-monitoring exports for Abbottabad district, Aug 2026),
same convention as test_indicators_vpd.py.

Requires `python run_weekly.py` to have been run at least once so the
processed parquet files exist.
"""
import pandas as pd
import pytest

from src.pipeline import indicators_monitoring as ind
from src.pipeline.run_monitoring import PROCESSED_DIR

pytestmark = pytest.mark.skipif(
    not (PROCESSED_DIR / "monitoring_rca_cases.parquet").exists(),
    reason="run `python run_weekly.py` first to generate data/processed/monitoring_*.parquet",
)


@pytest.fixture(scope="module")
def rca():
    return pd.read_parquet(PROCESSED_DIR / "monitoring_rca_cases.parquet")


@pytest.fixture(scope="module")
def sup():
    return pd.read_parquet(PROCESSED_DIR / "monitoring_supervisory_visits.parquet")


def test_rca_overview_matches_raw_counts(rca):
    overview = ind.rca_overview(rca)
    assert overview["total_children_assessed"] == 340
    assert overview["total_rca_visits"] == 34
    assert overview["districts_covered"] == 1


def test_rca_antigen_coverage_excludes_not_applicable_from_denominator(rca):
    rows = {r["antigen"]: r for r in ind.rca_antigen_coverage(rca)}
    bcg = rows["BCG"]
    assert bcg["assessed"] == 338  # 340 - 2 "Not Applicable"
    assert bcg["vaccinated"] == 337
    assert bcg["pct"] == pytest.approx(337 / 338 * 100)


def test_rca_zero_dose_summary_excludes_unassessed(rca):
    zero_dose = ind.rca_zero_dose_summary(rca)
    assert zero_dose["assessed_count"] == 320  # rows with Penta1 Vaccinated/Not Vaccinated
    assert zero_dose["zero_dose_count"] == 0  # no "Not Vaccinated" Penta1 in this sample
    assert zero_dose["zero_dose_pct"] == 0.0


def test_rca_district_breakdown_covers_all_districts_present(rca):
    rows = ind.rca_district_breakdown(rca)
    assert sum(r["children_assessed"] for r in rows) == len(rca)
    assert {r["district"] for r in rows} == set(rca["district"].unique())


def test_rca_sex_breakdown_sums_to_total_rows(rca):
    breakdown = ind.rca_sex_breakdown(rca)
    assert sum(breakdown.values()) == len(rca)


def test_rca_info_source_breakdown_splits_comma_separated_values(rca):
    breakdown = ind.rca_info_source_breakdown(rca)
    # 'LHW visit, Mosque Miking' (202 rows) + 'LHW visit' (82) + 'LHW visit, Mobile Miking' (3)
    assert breakdown["LHW visit"] == 202 + 82 + 3
    assert breakdown["Mosque Miking"] == 202 + 19 + 1


def test_supervisory_overview_matches_raw_counts(sup):
    overview = ind.supervisory_overview(sup)
    assert overview["total_visits"] == 63
    assert overview["districts_covered"] == 1


def test_supervisory_composite_scores_are_passthrough_from_source(sup):
    rows = {r["category"]: r for r in ind.supervisory_composite_scores(sup)}
    assert rows["Service Functionality"]["avg_pct"] == 0.0
    assert rows["Service Functionality"]["visits_scored"] == 63
    assert rows["Operations Quality"]["visits_scored"] == 63


def test_supervisory_compliance_items_sorted_ascending_by_yes_rate(sup):
    rows = ind.supervisory_compliance_items(sup)
    pcts = [r["pct"] for r in rows]
    assert pcts == sorted(pcts)
    # The inverted-polarity item must never appear in this Yes-is-good list.
    assert all("recapping" not in r["item"].lower() for r in rows)


def test_supervisory_practice_risk_flags_reports_recapping_separately(sup):
    rows = ind.supervisory_practice_risk_flags(sup)
    assert len(rows) == 1
    assert rows[0]["yes"] == 39
    assert rows[0]["answered"] == 63


def test_supervisory_cold_chain_flags_functional_exceeding_total(sup):
    cold_chain = ind.supervisory_cold_chain_summary(sup)
    assert cold_chain["sdd"]["inconsistent_visits"] == 1
    assert cold_chain["sdd"]["functional_units"] > cold_chain["sdd"]["total_units"]


def test_supervisory_fixed_site_open_rate_denominator_is_fixed_only(sup):
    rate = ind.supervisory_fixed_site_open_rate(sup)
    assert rate["answered"] == int((sup["site_type"] == "fixed").sum())


def test_supervisory_facility_rankings_top_and_bottom_are_disjoint(sup):
    rankings = ind.supervisory_facility_rankings(sup, "score_operations_quality", n=5)
    top_names = {r["health_facility"] for r in rankings["top"]}
    bottom_names = {r["health_facility"] for r in rankings["bottom"]}
    assert not (top_names & bottom_names)


def test_supervisory_district_breakdown_visit_counts_sum_to_total(sup):
    rows = ind.supervisory_district_breakdown(sup)
    assert sum(r["visits"] for r in rows) == len(sup)
