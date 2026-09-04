"""Clean raw VPD line lists into tidy per-disease case tables.

Column renaming is positional, not name-based: the source headers are messy
(a 2-row merged sub-header on the Pertussis sheet, trailing unnamed columns
on all four) in ways that make name-based mapping fragile. Position is
verified against the confirmed column count for each sheet at clean-time --
a shape mismatch raises immediately (fail loudly) rather than silently
misaligning columns.
"""
import numpy as np
import pandas as pd

from .config import (
    AGE_BUCKETS_MONTHS,
    DOSE_STATUS_LABELS,
    DOSE_STATUS_MAX_PLAUSIBLE,
    DOSE_STATUS_UNKNOWN,
    MSL_CLASSIFICATION_CANONICAL,
)

MSL_COLUMNS = [
    "sr_no", "province", "epi_week", "month_year", "reporting_hf", "reporting_district",
    "epid_number", "case_name", "father_name", "contact_number", "village", "uc", "tehsil",
    "district", "age_months", "sex", "rash_onset_date", "notification_date",
    "investigation_date", "doses_received", "last_dose_date", "travel_history",
    "clinical_presentation", "specimen_type", "specimen_collection_date", "specimen_sent_date",
    "specimen_received_lab_date", "quantity_adequate", "cold_chain_ok", "complications",
    "outcome", "lab_id", "report_sent_district_date", "lab_result_measles",
    "lab_result_rubella", "final_classification_raw", "epi_linked",
]

DIPHTHERIA_COLUMNS = [
    "sr_no", "province", "epi_week", "month_year", "reporting_hf", "reporting_district",
    "epid_number", "case_name", "father_name", "contact_number", "village", "uc", "tehsil",
    "district", "age_months", "sex", "onset_date", "notification_date", "investigation_date",
    "doses_received", "last_dose_date", "travel_history", "clinical_presentation",
    "specimen_sent_date", "specimen_received_lab_date", "quantity_adequate", "cold_chain_ok",
    "complications", "outcome", "lab_id", "report_sent_district_date", "lab_result",
    "final_classification_raw",
]

PERTUSSIS_COLUMNS_HEAD = [
    "sr_no", "province", "epi_week", "month_year", "reporting_hf", "reporting_district",
    "epid_number", "case_name", "father_name", "contact_number", "village", "uc", "tehsil",
    "district", "age_months", "sex", "onset_date", "notification_date", "investigation_date",
    "doses_received", "last_dose_date", "travel_history", "clinical_presentation",
    "specimen_sent_date", "specimen_received_lab_date", "quantity_adequate", "cold_chain_ok",
    "complications", "outcome", "lab_id", "report_sent_district_date",
]  # remaining trailing columns are unused/blank in the source

NNT_COLUMNS_HEAD = [
    "sr_no", "epid_number", "epi_week", "reporting_unit", "mother_name", "head_household_name",
    "age_days", "sex", "address", "uc", "tehsil", "district", "tt_doses_mother",
    "signs_symptoms", "onset_date", "notification_date", "investigation_date", "diagnosed_by",
    "outcome_raw", "antenatal_visits", "delivery_date", "delivery_conducted_by",
    "delivery_place", "cord_cutting_instrument", "cord_clamping_material",
]

NNT_OUTCOME_CANONICAL = {
    "died": "Death", "death": "Death",
    "improving": "Improving", "recovered": "Recovered",
    "alive with complications": "Alive with Complications",
    "with complication": "Alive with Complications",
    "lost to follow up": "Lost to Follow-up", "unknown": "Unknown",
}


# Direct patient identifiers -- dropped immediately after rename, before any
# indicator or output write. Not needed for any aggregate indicator and this
# is public-health line-list data that shouldn't be persisted into
# dashboard/bulletin-facing processed output. Village/UC/Tehsil/District are
# kept (needed for geographic drill-down, matches the coverage domain's
# granularity), same as the raw line list already displays them at
# investigation time.
PII_COLUMNS_TO_DROP = [
    "case_name", "father_name", "contact_number", "mother_name", "head_household_name",
]


def _rename_positional(df: pd.DataFrame, columns_head: list[str], sheet_label: str) -> pd.DataFrame:
    if df.shape[1] < len(columns_head):
        raise ValueError(
            f"{sheet_label} sheet has {df.shape[1]} columns, expected at least "
            f"{len(columns_head)}. The source layout may have changed -- check "
            f"src/pipeline/clean_vpd.py's column list against the actual sheet."
        )
    new_cols = columns_head + [f"_extra_{i}" for i in range(df.shape[1] - len(columns_head))]
    df = df.copy()
    df.columns = new_cols
    df = df.drop(columns=[c for c in PII_COLUMNS_TO_DROP if c in df.columns])
    return df


def _coerce_dates(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Date columns in these line lists mix real datetimes with the literal
    string '-' (meaning 'not yet done/recorded') -- coerce to real datetimes,
    turning '-' into NaT rather than leaving a column that mixes str and
    datetime (which breaks parquet writes and any date arithmetic)."""
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", format="mixed")
    return df


def _diphtheria_age_band(age_months):
    """5-year age band for the bulletin's diphtheria age-distribution chart,
    e.g. '1-5', '6-10', ... '26-30'. Under-1 cases get their own '<1y' band
    rather than being silently folded into '1-5' or dropped -- the source
    data does contain cases under 12 months (min age seen: 11 months)."""
    if age_months is None or (isinstance(age_months, float) and np.isnan(age_months)) or age_months < 0:
        return None
    years = int(age_months) // 12
    if years < 1:
        return "<1y"
    band_start = ((years - 1) // 5) * 5 + 1
    return f"{band_start}-{band_start + 4}"


def _bucket_age(age_months):
    if age_months is None or (isinstance(age_months, float) and np.isnan(age_months)):
        return None
    if age_months < 0:
        return None
    for lo, hi, label in AGE_BUCKETS_MONTHS:
        if hi is None:
            if age_months >= lo:
                return label
        elif lo <= age_months <= hi:
            return label
    return None


def _dose_status(value, log, period_id, level, entity):
    """Canonicalise a raw doses-received cell to 'Zero dose'/'1 dose'/'2 doses'/
    'Unknown'. A numeric value above DOSE_STATUS_MAX_PLAUSIBLE (e.g. the '111'
    seen in the Diphtheria sheet) is a data error: flagged and treated as
    Unknown, not silently kept as a real dose count."""
    if isinstance(value, str) and value.strip().lower() == "unknown":
        return DOSE_STATUS_UNKNOWN
    if isinstance(value, (int, float)) and not isinstance(value, bool) and not np.isnan(value):
        value = int(value)
        if 0 <= value <= DOSE_STATUS_MAX_PLAUSIBLE:
            return DOSE_STATUS_LABELS.get(value, f"{value} doses")
        log.flag(period_id, level, entity, "implausible_dose_count", detail=str(value))
        return DOSE_STATUS_UNKNOWN
    return DOSE_STATUS_UNKNOWN


def clean_msl(raw_df: pd.DataFrame, period_id: str, log):
    df = _rename_positional(raw_df, MSL_COLUMNS, "MSL LINE-LIST")
    df = _coerce_dates(df, [
        "rash_onset_date", "notification_date", "investigation_date", "last_dose_date",
        "specimen_collection_date", "specimen_sent_date", "specimen_received_lab_date",
        "report_sent_district_date",
    ])

    df["final_classification"] = df["final_classification_raw"].apply(
        lambda v: MSL_CLASSIFICATION_CANONICAL.get(str(v).strip().lower(), v) if pd.notna(v) else None
    )
    normalized_but_different = (
        df["final_classification_raw"].notna()
        & (df["final_classification"] != df["final_classification_raw"])
    )
    for _, row in df[normalized_but_different].iterrows():
        log.flag(period_id, "msl_case", row.get("epid_number", "?"), "classification_casing_normalized",
                  detail=f"{row['final_classification_raw']!r} -> {row['final_classification']!r}")

    negative_age = df["age_months"] < 0
    for _, row in df[negative_age.fillna(False)].iterrows():
        log.flag(period_id, "msl_case", row.get("epid_number", "?"), "invalid_negative_age",
                  detail=str(row["age_months"]))
    df["age_bucket"] = df["age_months"].apply(_bucket_age)

    df["dose_status"] = df.apply(
        lambda r: _dose_status(r["doses_received"], log, period_id, "msl_case", r.get("epid_number", "?")),
        axis=1,
    )

    df["is_specimen_collected"] = df["specimen_collection_date"].notna()
    df["is_specimen_adequate"] = df["quantity_adequate"].astype(str).str.strip().str.lower() == "yes"

    # Confirmed-measles / confirmed-rubella: defined from the lab result fields
    # (ground truth for lab-confirmed cases) OR an epi-linked classification
    # (cases confirmed by epidemiological link, which by definition have no lab
    # result). Not parsed from the free-text classification string.
    df["is_confirmed_measles"] = (
        (df["lab_result_measles"].astype(str).str.strip().str.lower() == "positive measles")
        | (df["final_classification"] == "Epidemiologically Confirmed Measles")
    )
    df["is_confirmed_rubella"] = (
        (df["lab_result_rubella"].astype(str).str.strip().str.lower() == "positive rubella")
        | (df["final_classification"] == "Epidemiologically Confirmed Rubella")
    )
    df["is_confirmed"] = df["is_confirmed_measles"] | df["is_confirmed_rubella"]

    # MCV1 is given at 9 months -- a suspected case under 9 months is not yet
    # due for a dose, so isn't a meaningful denominator for "was this case
    # vaccinated". Cases with an invalid (excluded) age are also not eligible.
    df["is_eligible_age"] = df["age_bucket"].notna() & (df["age_bucket"] != "0-8m")

    df["period_id"] = period_id
    return df


def clean_diphtheria(raw_df: pd.DataFrame, period_id: str, log):
    df = _rename_positional(raw_df, DIPHTHERIA_COLUMNS, "DIPHTHERIA LINE-LIST")
    df = _coerce_dates(df, [
        "onset_date", "notification_date", "investigation_date", "last_dose_date",
        "specimen_sent_date", "specimen_received_lab_date", "report_sent_district_date",
    ])
    df["age_bucket"] = df["age_months"].apply(_bucket_age)
    df["age_band_5yr"] = df["age_months"].apply(_diphtheria_age_band)
    df["dose_status"] = df.apply(
        lambda r: _dose_status(r["doses_received"], log, period_id, "diphtheria_case", r.get("epid_number", "?")),
        axis=1,
    )
    df["is_no_dpt_history"] = df["dose_status"] == "Zero dose"
    df["is_aged_5_plus"] = df["age_months"] >= 60
    df["is_lab_confirmed"] = df["final_classification_raw"].astype(str).str.strip() == "Laboratory Confirmed Diptheria"
    df["is_death"] = df["outcome"].astype(str).str.strip().str.lower() == "death"
    df["period_id"] = period_id
    return df


def clean_pertussis(raw_df: pd.DataFrame, period_id: str, log):
    df = _rename_positional(raw_df, PERTUSSIS_COLUMNS_HEAD, "Pertusis line-list")
    # This sheet has a 2-row merged sub-header ("Condition of Specimen" ->
    # "Quantity Adequate"/"Cold Chain OK", columns 25-26) but the loader only
    # skips 1 header row (VPD_HEADER_ROW), so the sub-header text itself is
    # read in as the first "data" row -- entirely blank except for those two
    # literal header strings, confirmed by direct inspection of the source
    # workbook. Every real case row has a serial number; this artifact row
    # does not, so it's the reliable way to identify and drop it (never
    # silently -- flagged in the quality log by row position since it has no
    # Epid number of its own).
    header_artifact = df["sr_no"].isna()
    for idx in df.index[header_artifact]:
        log.flag(period_id, "pertussis_case", f"row {idx}", "sheet_subheader_row_dropped",
                  detail="Blank row matching the 'Condition of Specimen' merged sub-header, not a real case")
    df = df.loc[~header_artifact].reset_index(drop=True)
    df = _coerce_dates(df, [
        "onset_date", "notification_date", "investigation_date", "last_dose_date",
        "specimen_sent_date", "specimen_received_lab_date", "report_sent_district_date",
    ])
    df["period_id"] = period_id
    return df


def clean_nnt(raw_df: pd.DataFrame, period_id: str, log):
    df = _rename_positional(raw_df, NNT_COLUMNS_HEAD, "NNT_LineList")
    df = _coerce_dates(df, ["onset_date", "notification_date", "investigation_date", "delivery_date"])
    df["outcome"] = df["outcome_raw"].apply(
        lambda v: NNT_OUTCOME_CANONICAL.get(str(v).strip().lower(), v) if pd.notna(v) else None
    )
    df["is_death"] = df["outcome"] == "Death"
    df["period_id"] = period_id
    return df
