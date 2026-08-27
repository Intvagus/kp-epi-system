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


# ---------------------------------------------------------------------------
# MSL-focused analytical additions (reference: weekly "Measles/Rubella KPIs &
# Data Quality Issues" surveillance status report). Each function reads only
# columns clean_vpd.clean_msl already produces -- no new raw fields, no
# fabricated denominators.
# ---------------------------------------------------------------------------

def reporting_footprint(df: pd.DataFrame) -> dict:
    """Count of distinct reporting health facilities and UCs that have
    submitted at least one case -- 'how much of the province is reporting',
    not a case-count metric."""
    return {
        "reporting_health_facilities": int(df["reporting_hf"].nunique(dropna=True)),
        "reporting_ucs": int(df["uc"].nunique(dropna=True)),
        "reporting_districts": int(df["district"].nunique(dropna=True)),
    }


def duplicate_epid_summary(df: pd.DataFrame) -> dict:
    """Rows sharing the same Epid number are a data-entry/reporting-chain
    duplication, not two real cases. Flagged here (never dropped from the
    dataset itself -- the underlying rows still count everywhere else)."""
    dup_mask = df["epid_number"].notna() & df["epid_number"].duplicated(keep=False)
    dup = df[dup_mask]
    by_district = (
        dup.groupby("district").size().reset_index(name="duplicate_rows")
        .sort_values("duplicate_rows", ascending=False).to_dict(orient="records")
    )
    return {
        "duplicate_epid_count": int(df.loc[dup_mask, "epid_number"].nunique()),
        "duplicate_row_count": int(dup_mask.sum()),
        "by_district": by_district,
    }


def under_eligible_age_vaccinated_anomaly(df: pd.DataFrame) -> dict:
    """Cases under 9 months (not yet MCV1-eligible) with a recorded dose
    count > 0 are a plausible data-entry anomaly (wrong age, wrong dose
    field, or a dose given outside the routine schedule) -- surfaced for
    field verification, not treated as fact."""
    under_age = df[~df["is_eligible_age"] & df["age_bucket"].notna()]
    anomaly = under_age[~under_age["dose_status"].isin(["Zero dose", "Unknown"])]
    by_district = (
        anomaly.groupby("district").size().reset_index(name="case_count")
        .sort_values("case_count", ascending=False).to_dict(orient="records")
    )
    return {
        "under_age_case_count": int(len(under_age)),
        "anomaly_count": int(len(anomaly)),
        "by_district": by_district,
    }


_COMPLETENESS_FIELDS = {
    "quantity_adequate": "Specimen Quantity Adequate",
    "cold_chain_ok": "Cold Chain OK",
    "lab_id": "Lab ID Number",
    "report_sent_district_date": "Report Sent to District Date",
    "last_dose_date": "Last Vaccine Dose Date",
    "investigation_date": "Investigation Date",
    "specimen_collection_date": "Specimen Collection Date",
    "complications": "Complications",
    "outcome": "Outcome",
    "travel_history": "Travel History",
}


def field_completeness(df: pd.DataFrame) -> list[dict]:
    """% of suspected cases with a non-missing value in each of a fixed set
    of fields the reference report tracks for data-quality purposes. Sorted
    ascending by completeness (worst-completed field first)."""
    n = len(df)
    rows = []
    for col, label in _COMPLETENESS_FIELDS.items():
        if col not in df.columns or n == 0:
            continue
        present = df[col].notna()
        if df[col].dtype == object:
            present &= df[col].astype(str).str.strip().ne("")
        pct = present.sum() / n * 100
        rows.append({"field": label, "pct_complete": pct, "missing_count": int(n - present.sum())})
    rows.sort(key=lambda r: r["pct_complete"])
    return rows


_LAB_POSITIVE = {"positive measles", "positive rubella"}
_LAB_NEGATIVE = {"negative measles", "negative rubella"}
_CLASS_CONFIRMED = {
    "laboratory confirmed measles", "laboratory confirmed measles and rubella",
    "double infection", "epidemiologically confirmed measles",
    "epidemiologically confirmed rubella",
}
_CLASS_DISCARDED = {"discarded"}
_CLASS_PENDING = {"pending classification"}


def _lab_group(row) -> str:
    m = str(row.get("lab_result_measles")).strip().lower()
    r = str(row.get("lab_result_rubella")).strip().lower()
    if m in _LAB_POSITIVE or r in _LAB_POSITIVE:
        return "Positive"
    if m in _LAB_NEGATIVE or r in _LAB_NEGATIVE:
        return "Negative"
    return "Missing/Not Done"


def _classification_group(value) -> str:
    v = str(value).strip().lower()
    if v in _CLASS_CONFIRMED:
        return "Confirmed"
    if v in _CLASS_DISCARDED:
        return "Discarded"
    if v in _CLASS_PENDING:
        return "Pending"
    return "Other (Clinically Compatible etc.)"


def classification_discordance_matrix(df: pd.DataFrame) -> dict:
    """Cross-tab of lab result (Positive/Negative/Missing) against final
    classification group (Confirmed/Discarded/Pending/Other). Two specific
    combinations are flagged as discordant for field review: a Positive lab
    result classified as Discarded, and a Negative lab result classified as
    Confirmed -- everything else is an expected pairing."""
    lab_group = df.apply(_lab_group, axis=1)
    class_group = df["final_classification_raw"].apply(_classification_group)
    matrix = pd.crosstab(lab_group, class_group)
    cols = ["Confirmed", "Discarded", "Pending", "Other (Clinically Compatible etc.)"]
    rows_order = ["Positive", "Negative", "Missing/Not Done"]
    matrix = matrix.reindex(index=rows_order, columns=cols, fill_value=0)
    flagged = {
        ("Positive", "Discarded"),
        ("Negative", "Confirmed"),
    }
    cells = []
    for lab_row in rows_order:
        for col in cols:
            count = int(matrix.loc[lab_row, col])
            cells.append({
                "lab_result": lab_row, "classification": col, "count": count,
                "flagged": (lab_row, col) in flagged and count > 0,
            })
    return {
        "cells": cells,
        "flagged_count": sum(c["count"] for c in cells if c["flagged"]),
    }


def lab_confirmed_dose_validation(df: pd.DataFrame) -> dict:
    """Cases lab-confirmed as measles/rubella (is_confirmed) with 2 or 1
    prior vaccine doses recorded are unusual (MCV is highly effective) and
    worth field validation -- surfaced as counts + the districts they cluster
    in, not asserted as errors."""
    confirmed = df[df["is_confirmed"]]
    two_dose = confirmed[confirmed["dose_status"] == "2 doses"]
    one_dose = confirmed[confirmed["dose_status"] == "1 dose"]
    by_district_2dose = (
        two_dose.groupby("district").size().reset_index(name="case_count")
        .sort_values("case_count", ascending=False).head(10).to_dict(orient="records")
    )
    return {
        "confirmed_case_count": int(len(confirmed)),
        "two_dose_count": int(len(two_dose)),
        "one_dose_count": int(len(one_dose)),
        "dose_status_breakdown": confirmed["dose_status"].value_counts(dropna=False).to_dict(),
        "top_districts_two_dose": by_district_2dose,
    }


def timeliness_buckets(df: pd.DataFrame) -> dict:
    """Rash-onset -> notification delay, bucketed into <=48h / 3-7 days /
    >7 days, for cases where both dates are present and notification is not
    before onset (a negative delay is a date-entry error, reported
    separately rather than folded into a bucket)."""
    valid = df[df["rash_onset_date"].notna() & df["notification_date"].notna()]
    delta_days = (valid["notification_date"] - valid["rash_onset_date"]).dt.total_seconds() / 86400
    negative = int((delta_days < 0).sum())
    sane = delta_days[delta_days >= 0]
    buckets = {
        "<=48h": int((sane <= 2).sum()),
        "3-7 days": int(((sane > 2) & (sane <= 7)).sum()),
        ">7 days": int((sane > 7).sum()),
    }
    return {
        "buckets": buckets,
        "evaluable_count": int(len(sane)),
        "negative_delay_count": negative,
        "median_days": float(sane.median()) if len(sane) else None,
    }


def sex_breakdown(df: pd.DataFrame) -> dict:
    return df["sex"].value_counts(dropna=False).to_dict()


def outcome_breakdown(df: pd.DataFrame) -> dict:
    return df["outcome"].value_counts(dropna=False).to_dict()


_COMPLICATION_TYPES = ["Pneumonia", "Diarrhea", "Encephalitis", "Other"]


def complications_breakdown(df: pd.DataFrame) -> dict:
    """The complications field is comma-separated free text (e.g.
    'Pneumonia,Diarrhea') -- split and counted per individual complication
    type, plus a 'None recorded' bucket for suspected cases with no
    complication text at all."""
    counts = {c: 0 for c in _COMPLICATION_TYPES}
    none_recorded = 0
    for value in df["complications"]:
        if pd.isna(value) or str(value).strip() == "":
            none_recorded += 1
            continue
        parts = [p.strip() for p in str(value).split(",")]
        for p in parts:
            if p in counts:
                counts[p] += 1
    counts["None recorded"] = none_recorded
    return counts


def daily_epi_curve(df: pd.DataFrame) -> list[dict]:
    """Daily suspected-case counts by rash onset date, plus a 7-day trailing
    rolling average -- the epi-curve view the weekly-aggregated
    msl_weekly_trend can't show. Cases with no rash onset date recorded are
    excluded (dateless rows can't place on a daily timeline)."""
    valid = df[df["rash_onset_date"].notna()].copy()
    if valid.empty:
        return []
    valid["onset_day"] = valid["rash_onset_date"].dt.date
    daily = valid.groupby("onset_day").size().reset_index(name="case_count").sort_values("onset_day")
    full_range = pd.date_range(daily["onset_day"].min(), daily["onset_day"].max(), freq="D").date
    daily = daily.set_index("onset_day").reindex(full_range, fill_value=0).rename_axis("onset_day").reset_index()
    daily["rolling_7d_avg"] = daily["case_count"].rolling(7, min_periods=1).mean()
    daily["onset_day"] = daily["onset_day"].astype(str)
    return daily.to_dict(orient="records")


def top_districts_by_cases(df: pd.DataFrame, n: int = 10) -> list[dict]:
    g = district_breakdown(df)
    return g.sort_values("suspected", ascending=False).head(n).to_dict(orient="records")


def district_action_priority(df: pd.DataFrame) -> list[dict]:
    """Per-district synthesis table: case load, confirmed cases, data-quality
    issue count (duplicate Epids + under-age-vaccinated anomalies + missing
    lab result), and a Critical/Action/Monitor priority tier.

    Priority is relative to this province's own current distribution, not a
    fixed case-count cutoff (with ~37 districts nearly all having at least
    one confirmed case, an absolute 'any confirmed case = Critical' rule
    would just label everything Critical and stop being useful): a district
    lands in the top quartile of confirmed cases, or has an unusually high
    data-quality issue count for the province, gets Critical; at/above the
    province median confirmed count, or any issues at all, gets Action;
    everything else is Monitor. Thresholds are recomputed from the data on
    every run -- never a hardcoded district list or number."""
    base = district_breakdown(df)
    base["confirmed"] = base["measles_confirmed"] + base["rubella_confirmed"]

    dup = duplicate_epid_summary(df)["by_district"]
    dup_map = {r["district"]: r["duplicate_rows"] for r in dup}
    anomaly = under_eligible_age_vaccinated_anomaly(df)["by_district"]
    anomaly_map = {r["district"]: r["case_count"] for r in anomaly}
    missing_lab = df[df["lab_result_measles"].isna() & df["lab_result_rubella"].isna()]
    missing_lab_map = missing_lab.groupby("district").size().to_dict()

    issues_by_district = {}
    for district in base["district"]:
        issues_by_district[district] = (
            int(dup_map.get(district, 0)) + int(anomaly_map.get(district, 0)) + int(missing_lab_map.get(district, 0))
        )

    confirmed_q75 = base["confirmed"].quantile(0.75) if len(base) else 0
    confirmed_median = base["confirmed"].median() if len(base) else 0
    issues_q75 = pd.Series(list(issues_by_district.values())).quantile(0.75) if issues_by_district else 0

    rows = []
    for _, r in base.iterrows():
        district = r["district"]
        confirmed = int(r["confirmed"])
        issues = issues_by_district[district]
        if (confirmed_q75 > 0 and confirmed >= confirmed_q75) or (issues_q75 > 0 and issues >= issues_q75):
            priority = "Critical"
        elif (confirmed_median > 0 and confirmed >= confirmed_median) or issues > 0:
            priority = "Action"
        else:
            priority = "Monitor"
        rows.append({
            "district": district,
            "suspected": int(r["suspected"]),
            "confirmed": confirmed,
            "data_quality_issues": issues,
            "priority": priority,
        })
    priority_order = {"Critical": 0, "Action": 1, "Monitor": 2}
    rows.sort(key=lambda r: (priority_order[r["priority"]], -r["suspected"]))
    return rows
