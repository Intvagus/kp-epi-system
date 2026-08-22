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


def test_diphtheria_weekly_trend_sums_to_ytd_total(diphtheria):
    trend = ind.weekly_case_counts(diphtheria)
    assert trend["case_count"].sum() == 167


def test_nnt_death_outcome_synonyms_are_merged(nnt):
    # Source has both 'Died' (34) and 'Death' (5) as literal outcome strings
    # for the same concept -- clean_vpd.NNT_OUTCOME_CANONICAL merges them.
    summary = ind.nnt_summary(nnt)
    assert summary["deaths"] == 34 + 5
    assert summary["case_count"] == 132
