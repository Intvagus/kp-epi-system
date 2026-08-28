"""VPD indicator functions tested against the real cleaned line-list output
(data/processed/vpd_*.parquet), pinned to numbers confirmed by direct
inspection of KP VPDs Line List Week 1-32,2026.xlsx, so these tests catch a
real regression, not just an invented one.

Requires `python run_weekly.py` to have been run at least once so the
processed parquet files exist.
"""
import pandas as pd
import pytest

from src.pipeline import indicators_vpd as ind
from src.pipeline.run_vpd import PROCESSED_DIR

pytestmark = pytest.mark.skipif(
    not (PROCESSED_DIR / "vpd_msl_cases.parquet").exists(),
    reason="run `python run_weekly.py` first to generate data/processed/vpd_*.parquet",
)


@pytest.fixture(scope="module")
def msl():
    return pd.read_parquet(PROCESSED_DIR / "vpd_msl_cases.parquet")


@pytest.fixture(scope="module")
def diphtheria():
    return pd.read_parquet(PROCESSED_DIR / "vpd_diphtheria_cases.parquet")


@pytest.fixture(scope="module")
def nnt():
    return pd.read_parquet(PROCESSED_DIR / "vpd_nnt_cases.parquet")


def test_msl_suspected_ytd_matches_full_line_list_row_count(msl):
    assert ind.suspected_case_count(msl) == 10336


def test_msl_classification_casing_duplicate_is_merged(msl):
    breakdown = ind.classification_breakdown(msl)
    # Source has 'Laboratory Confirmed Measles' (3795) and a lowercase-'l'
    # duplicate (35) that must be counted as one category, not two.
    assert breakdown["Laboratory Confirmed Measles"] == 3795 + 35
    assert "laboratory Confirmed Measles" not in breakdown


def test_msl_dose_status_breakdown_matches_raw_distribution(msl):
    breakdown = ind.dose_status_breakdown(msl)
    assert breakdown == {"Zero dose": 6415, "1 dose": 1625, "2 doses": 1315, "Unknown": 981}


def test_msl_age_distribution_excludes_the_one_negative_age_row(msl):
    breakdown = ind.age_distribution(msl)
    assert sum(breakdown.values()) == 10336 - 1  # 1 row flagged invalid_negative_age


def test_msl_sample_collection_rate_is_a_sane_percentage(msl):
    rate = ind.sample_collection_rate(msl)
    assert 0 <= rate <= 100


def test_msl_district_breakdown_covers_all_37_districts(msl):
    breakdown = ind.district_breakdown(msl)
    assert len(breakdown) == 37


def test_diphtheria_lab_confirmed_count_matches_raw(diphtheria):
    summary = ind.diphtheria_summary(diphtheria)
    assert summary["case_count"] == 167
    assert summary["lab_confirmed_count"] == 35
    assert summary["deaths"] == 1


def test_dose_status_breakdown_any_disease_includes_both_confirmed_flags(msl):
    combined = ind.dose_status_breakdown(msl, confirmed_only=True, disease="any")
    measles_only = ind.dose_status_breakdown(msl, confirmed_only=True, disease="measles")
    rubella_only = ind.dose_status_breakdown(msl, confirmed_only=True, disease="rubella")
    # 'any' (measles OR rubella confirmed) must be >= either single-disease breakdown
    for status in combined:
        assert combined[status] >= measles_only.get(status, 0)
        assert combined[status] >= rubella_only.get(status, 0)


def test_dose_status_breakdown_eligible_only_excludes_under_9_months(msl):
    all_suspected = sum(ind.dose_status_breakdown(msl).values())
    eligible_only = sum(ind.dose_status_breakdown(msl, eligible_only=True).values())
    # is_eligible_age excludes both the '0-8m' bucket AND rows with no valid
    # age bucket at all (the 1 invalid-negative-age row) -- see clean_vpd.py.
    not_eligible = int((~msl["is_eligible_age"]).sum())
    assert all_suspected - eligible_only == not_eligible


def test_diphtheria_age_band_counts_sums_to_total_valid_age_rows(diphtheria):
    bands = ind.diphtheria_age_band_counts(diphtheria)
    assert sum(bands.values()) == diphtheria["age_band_5yr"].notna().sum()
    assert "<1y" in bands  # source has at least one case under 12 months (min age seen: 11)


def test_week_over_week_delta_matches_raw_week_counts(msl):
    result = ind.week_over_week_delta(msl, 32)
    assert result["prior_week"] == 31
    assert result["this_week_count"] == int((msl["epi_week"] == 32).sum())
    assert result["prior_week_count"] == int((msl["epi_week"] == 31).sum())
    assert result["delta"] == result["this_week_count"] - result["prior_week_count"]


def test_week_over_week_delta_none_for_first_week(msl):
    assert ind.week_over_week_delta(msl, 1) is None


def test_msl_weekly_trend_sums_to_ytd_total(msl):
    trend = ind.msl_weekly_trend(msl)
    assert trend["suspected"].sum() == 10336
    assert list(trend["epi_week"]) == sorted(trend["epi_week"])


def test_msl_weekly_trend_discarded_matches_raw_classification_count(msl):
    trend = ind.msl_weekly_trend(msl)
    assert trend["discarded"].sum() == int((msl["final_classification"] == "Discarded").sum())
    assert trend["measles_confirmed"].sum() == int(msl["is_confirmed_measles"].sum())
    assert trend["rubella_confirmed"].sum() == int(msl["is_confirmed_rubella"].sum())


def test_diphtheria_weekly_trend_sums_to_ytd_total(diphtheria):
    trend = ind.weekly_case_counts(diphtheria)
    assert trend["case_count"].sum() == 167


def test_reporting_footprint_counts_distinct_hfs_and_ucs(msl):
    footprint = ind.reporting_footprint(msl)
    assert footprint["reporting_health_facilities"] == 298
    assert footprint["reporting_ucs"] == 1076
    assert footprint["reporting_districts"] == 37


def test_duplicate_epid_summary_matches_raw_duplicate_count(msl):
    dup = ind.duplicate_epid_summary(msl)
    assert dup["duplicate_epid_count"] == 40
    assert dup["duplicate_row_count"] == 91
    assert dup["by_district"][0]["duplicate_rows"] >= dup["by_district"][-1]["duplicate_rows"]


def test_under_eligible_age_vaccinated_anomaly_matches_direct_count(msl):
    anomaly = ind.under_eligible_age_vaccinated_anomaly(msl)
    assert anomaly["under_age_case_count"] == 2032
    assert anomaly["anomaly_count"] == 24


def test_field_completeness_sorted_worst_first(msl):
    rows = ind.field_completeness(msl)
    pcts = [r["pct_complete"] for r in rows]
    assert pcts == sorted(pcts)
    assert all(0 <= p <= 100 for p in pcts)


def test_classification_discordance_matrix_has_twelve_cells(msl):
    result = ind.classification_discordance_matrix(msl)
    assert len(result["cells"]) == 12
    assert result["flagged_count"] > 0
    total = sum(c["count"] for c in result["cells"])
    assert total == len(msl)


def test_lab_confirmed_dose_validation_counts_are_sane(msl):
    result = ind.lab_confirmed_dose_validation(msl)
    assert result["confirmed_case_count"] == int(msl["is_confirmed"].sum())
    assert result["two_dose_count"] + result["one_dose_count"] <= result["confirmed_case_count"]
    assert len(result["top_districts_two_dose"]) <= 10


def test_timeliness_buckets_sum_to_evaluable_count(msl):
    result = ind.timeliness_buckets(msl)
    assert sum(result["buckets"].values()) == result["evaluable_count"]
    assert result["negative_delay_count"] == 83


def test_sex_breakdown_covers_all_rows(msl):
    breakdown = ind.sex_breakdown(msl)
    assert sum(breakdown.values()) == len(msl)


def test_outcome_breakdown_covers_all_rows(msl):
    breakdown = ind.outcome_breakdown(msl)
    assert sum(breakdown.values()) == len(msl)
    assert breakdown.get("Death") == 29


def test_complications_breakdown_none_recorded_matches_nan_count(msl):
    breakdown = ind.complications_breakdown(msl)
    assert breakdown["None recorded"] == int(msl["complications"].isna().sum())
    assert sum(breakdown.values()) >= len(msl)  # multi-complication rows count in >1 bucket


def test_daily_epi_curve_has_no_gaps_and_rolling_avg_is_bounded(msl):
    curve = ind.daily_epi_curve(msl)
    assert len(curve) > 0
    counts = [r["case_count"] for r in curve]
    assert sum(counts) == int(msl["rash_onset_date"].notna().sum())
    assert all(r["rolling_7d_avg"] <= max(counts) for r in curve)


def test_top_districts_by_cases_is_sorted_descending(msl):
    top = ind.top_districts_by_cases(msl, 5)
    assert len(top) == 5
    suspected = [r["suspected"] for r in top]
    assert suspected == sorted(suspected, reverse=True)
    assert top[0]["district"] == "D.I. Khan"


def test_district_action_priority_covers_all_districts_and_orders_by_priority(msl):
    rows = ind.district_action_priority(msl)
    assert len(rows) == msl["district"].nunique()
    priority_rank = {"Critical": 0, "Action": 1, "Monitor": 2}
    ranks = [priority_rank[r["priority"]] for r in rows]
    assert ranks == sorted(ranks)


def test_nnt_death_outcome_synonyms_are_merged(nnt):
    # Source has both 'Died' (34) and 'Death' (5) as literal outcome strings
    # for the same concept -- clean_vpd.NNT_OUTCOME_CANONICAL merges them.
    summary = ind.nnt_summary(nnt)
    assert summary["deaths"] == 34 + 5
    assert summary["case_count"] == 132
