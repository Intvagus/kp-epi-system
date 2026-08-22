"""VPD surveillance indicator formulas, one function each -- the single source
of truth the dashboard and bulletin both read from (via data/processed/vpd_*),
never recomputing themselves. See CLAUDE.md "Confirmed VPD decisions" for what
is deliberately NOT computed here (AFP, per-population incidence rates) and why.
"""
import pandas as pd


def suspected_case_count(df: pd.DataFrame, epi_week: int | None = None) -> int:
    """Count of suspected cases. With epi_week=None, this is the cumulative
    (year-to-date) count; with epi_week set, it's that single week's count."""
    if epi_week is None:
        return len(df)
    return int((df["epi_week"] == epi_week).sum())


def classification_breakdown(df: pd.DataFrame) -> dict:
    """Count of cases per final_classification category (already
    case-normalized in clean_vpd.clean_msl). Reported as-found rather than
    force-fit into a shorter category list -- see CLAUDE.md open question re:
    'Laboratory Confirmed Measles and Rubella' vs 'Double Infection'."""
    return df["final_classification"].value_counts(dropna=False).to_dict()


def sample_collection_rate(df: pd.DataFrame) -> float | None:
    """% of suspected cases with a specimen collection date recorded =
    is_specimen_collected count / total suspected cases x 100."""
    if len(df) == 0:
        return None
    return df["is_specimen_collected"].sum() / len(df) * 100


def sample_adequacy_rate(df: pd.DataFrame) -> float | None:
    """% of COLLECTED specimens marked Quantity-Adequate = Yes. Denominator is
    cases with a specimen collected, not all suspected cases -- adequacy can
    only be assessed for specimens that exist."""
    collected = df[df["is_specimen_collected"]]
    if len(collected) == 0:
        return None
    return collected["is_specimen_adequate"].sum() / len(collected) * 100


_CONFIRMED_COLS = {"measles": "is_confirmed_measles", "rubella": "is_confirmed_rubella", "any": "is_confirmed"}


def dose_status_breakdown(df: pd.DataFrame, confirmed_only: bool = False,
                           disease: str = "measles", eligible_only: bool = False) -> dict:
    """MCV vaccination status (Zero dose/1 dose/2 doses/Unknown) of either all
    suspected cases or only confirmed cases. `disease` selects which
    is_confirmed_* flag to filter on when confirmed_only=True ('measles',
    'rubella', or 'any' = measles OR rubella). `eligible_only` restricts to
    cases aged >= 9 months (is_eligible_age -- MCV1 is given at 9 months, so
    younger cases aren't a meaningful vaccination-status denominator)."""
    subset = df
    if confirmed_only:
        subset = subset[subset[_CONFIRMED_COLS[disease]]]
    if eligible_only:
        subset = subset[subset["is_eligible_age"]]
    return subset["dose_status"].value_counts(dropna=False).to_dict()


def age_distribution(df: pd.DataFrame) -> dict:
    """Suspected-case counts per age bucket (0-8m/9-23m/24-59m/60m+). Cases
    with an invalid (negative) age are excluded from this breakdown -- they
    remain in every other count (see clean_vpd.clean_msl)."""
    return df["age_bucket"].value_counts(dropna=True).to_dict()


def district_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Per-district: suspected case count, measles-confirmed count,
    rubella-confirmed count. Confirmed counts use is_confirmed_measles/
    is_confirmed_rubella (see clean_vpd.clean_msl for the exact definition)."""
    g = df.groupby("district").agg(
        suspected=("epid_number", "count"),
        measles_confirmed=("is_confirmed_measles", "sum"),
        rubella_confirmed=("is_confirmed_rubella", "sum"),
    ).reset_index()
    return g


def diphtheria_summary(df: pd.DataFrame, epi_week: int | None = None) -> dict:
    """Diphtheria weekly/cumulative summary: case count, districts affected,
    lab-confirmed count, % with no recorded DPT history (dose_status ==
    'Zero dose' -- confirmed with user as the direct proxy for DPT history in
    this dataset), % aged 5 years+ (age_months >= 60), and death count."""
    subset = df if epi_week is None else df[df["epi_week"] == epi_week]
    n = len(subset)
    return {
        "case_count": n,
        "districts_affected": subset["district"].nunique(),
        "lab_confirmed_count": int(subset["is_lab_confirmed"].sum()),
        "pct_no_dpt_history": (subset["is_no_dpt_history"].sum() / n * 100) if n else None,
        "pct_aged_5_plus": (subset["is_aged_5_plus"].sum() / n * 100) if n else None,
        "deaths": int(subset["is_death"].sum()),
    }


def diphtheria_age_band_counts(df: pd.DataFrame) -> dict:
    """Diphtheria case counts per 5-year age band (see
    clean_vpd._diphtheria_age_band). Bands are whatever the data actually
    contains -- not padded or capped to match any particular chart width."""
    return df["age_band_5yr"].value_counts(dropna=True).to_dict()


def week_over_week_delta(df: pd.DataFrame, week: int) -> dict | None:
    """This week's case count vs. the immediately preceding week, for the
    bulletin's auto-generated comparison sentence. Returns None if there's no
    prior week in the data to compare against (e.g. week 1)."""
    prior_weeks = df.loc[df["epi_week"] < week, "epi_week"]
    if prior_weeks.empty:
        return None
    prior_week = int(prior_weeks.max())
    this_count = int((df["epi_week"] == week).sum())
    prior_count = int((df["epi_week"] == prior_week).sum())
    delta = this_count - prior_count
    pct_change = (delta / prior_count * 100) if prior_count else None
    return {
        "this_week": week, "this_week_count": this_count,
        "prior_week": prior_week, "prior_week_count": prior_count,
        "delta": delta, "pct_change": pct_change,
    }


def pertussis_district_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Cumulative pertussis case count by district."""
    return df.groupby("district").size().reset_index(name="case_count")


def msl_weekly_trend(df: pd.DataFrame) -> pd.DataFrame:
    """Per-epi-week suspected / measles-confirmed / rubella-confirmed counts,
    sorted by week. The single source for the dashboard's Surveillance trend
    chart AND the bulletin's district-wise/weekly charts -- computed once
    here, never re-aggregated independently in template code."""
    g = df.groupby("epi_week").agg(
        suspected=("epid_number", "count"),
        measles_confirmed=("is_confirmed_measles", "sum"),
        rubella_confirmed=("is_confirmed_rubella", "sum"),
    ).reset_index().sort_values("epi_week")
    return g


def weekly_case_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Per-epi-week case count. Used for Diphtheria/Pertussis/NNT trend
    charts (diphtheria panel's 'cases-over-time' chart per the bulletin
    layout in the build brief)."""
    return df.groupby("epi_week").size().reset_index(name="case_count").sort_values("epi_week")


def nnt_summary(df: pd.DataFrame, epi_week: int | None = None) -> dict:
    """NNT weekly/cumulative case count and deaths, overall and by district."""
    subset = df if epi_week is None else df[df["epi_week"] == epi_week]
    by_district = subset.groupby("district").size().reset_index(name="case_count")
    return {
        "case_count": len(subset),
        "deaths": int(subset["is_death"].sum()),
        "by_district": by_district,
    }
