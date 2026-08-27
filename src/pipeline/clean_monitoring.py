"""Clean raw Monitoring-domain tables (RCA child-level assessment,
Supervisory Checklist facility visits) into tidy frames.

Both source files are HTML-table exports with long, punctuation-heavy header
text (quotes, apostrophes, mixed encoding -- e.g. RCA's "Respondent's
relationship" column decodes with a mangled apostrophe). Column access here
is positional, not name-based, for the same reason clean_vpd.py's MSL sheet
is positional: exact header strings are fragile, column order is the one
thing the export format actually guarantees. A shape mismatch raises
immediately (fail loudly) rather than silently misaligning columns.
"""
import numpy as np
import pandas as pd

from .config import RCA_STATUS_CANONICAL, RCA_VACCINE_ANTIGENS

# RCA_Report_2.xls: 50 columns, one row per child assessed during an RCA visit.
RCA_COLUMNS = [
    "sr_no", "record_id", "district", "tehsil", "uc", "village", "gps_lat", "gps_lng",
    "monitor_name", "monitor_id", "monitor_designation", "monitor_agency", "visit_date",
    "area_type", "hard_to_reach_area", "high_risk_population", "child_name", "father_name",
    "respondent_relationship", "sex", "child_address", "age_months_raw", "age_group",
    "last_vaccinated_where", "bcg", "hepb", "opv0", "opv1", "opv2", "opv3", "rota1", "rota2",
    "penta1", "penta2", "penta3", "pcv1", "pcv2", "pcv3", "ipv1", "ipv2", "tcv", "mr1", "mr2",
    "vaccine_source", "qr_code", "non_vaccination_reason", "vaccination_info_source",
    "gps_lat_child", "gps_lng_child", "comments",
]

PII_COLUMNS_TO_DROP = [
    "child_name", "father_name", "child_address", "gps_lat", "gps_lng",
    "gps_lat_child", "gps_lng_child",
]

RCA_ANTIGEN_FIELD_MAP = {
    "BCG": "bcg", "HepB": "hepb", "OPV 0": "opv0", "OPV 1": "opv1", "OPV 2": "opv2",
    "OPV 3": "opv3", "Rota 1": "rota1", "Rota 2": "rota2", "Penta 1": "penta1",
    "Penta 2": "penta2", "Penta 3": "penta3", "PCV 1": "pcv1", "PCV 2": "pcv2",
    "PCV 3": "pcv3", "IPV I": "ipv1", "IPV II": "ipv2", "TCV": "tcv", "MR I": "mr1", "MR II": "mr2",
}
RCA_ANTIGEN_FIELDS = [RCA_ANTIGEN_FIELD_MAP[a] for a in RCA_VACCINE_ANTIGENS]


def _canonical_status(v):
    if pd.isna(v):
        return None
    key = str(v).strip().lower()
    return RCA_STATUS_CANONICAL.get(key, v)


def clean_rca(raw_df: pd.DataFrame, period_id: str, log) -> pd.DataFrame:
    if raw_df.shape[1] != len(RCA_COLUMNS):
        raise ValueError(
            f"RCA file has {raw_df.shape[1]} columns, expected {len(RCA_COLUMNS)}. "
            f"The source layout may have changed -- check src/pipeline/clean_monitoring.py's RCA_COLUMNS."
        )
    df = raw_df.copy()
    df.columns = RCA_COLUMNS
    df = df.drop(columns=[c for c in PII_COLUMNS_TO_DROP if c in df.columns])

    df["visit_date"] = pd.to_datetime(df["visit_date"], errors="coerce", format="mixed")
    df["age_months_raw"] = pd.to_numeric(df["age_months_raw"], errors="coerce")

    for field in RCA_ANTIGEN_FIELDS:
        df[field] = df[field].apply(_canonical_status)

    # Zero-dose = Penta1 not received (WHO's standard zero-dose definition),
    # restricted to children for whom Penta1 was actually assessed as
    # applicable -- "Not Applicable"/unassessed rows can't be classified
    # either way and are excluded from this flag (still counted everywhere else).
    df["is_penta1_assessed"] = df["penta1"].isin(["Vaccinated", "Not Vaccinated"])
    df["is_zero_dose"] = df["is_penta1_assessed"] & (df["penta1"] == "Not Vaccinated")

    df["period_id"] = period_id
    return df


# Supervisory_Checklist_Report.xls: 137 columns, one row per supervisory
# visit. Only the columns actually used for indicators are extracted here by
# position -- the remaining ~100 free-text/microplan-table columns are kept
# on the raw frame untouched (see run_monitoring.py) for the Excel export,
# not renamed or parsed.
SUPERVISORY_COL_COUNT = 137
SUPERVISORY_FIELD_INDEX = {
    "district": 1, "tehsil": 2, "uc": 3, "health_facility": 4,
    "site_type": 9, "hf_type": 10, "monitor_name": 11,
    "monitor_designation": 13, "monitor_agency": 14, "visit_datetime": 15,
    "fixed_site_open": 16,
    "signboard_displayed": 19, "charts_displayed": 20, "charts_updated": 21,
    "schedule_displayed": 22, "uc_map_displayed": 23,
    "room_spacious": 24, "privacy_area": 25,
    "backup_power_available": 26, "backup_power_operational": 27,
    "microplan_available_with_vaccinator": 28,
    "vaccine_carrier_standard": 30,
    "zero_dose_list_used": 31,
    "uc_microplan_copy_at_center": 32,
    "ilr_functional_count": 35,
    "sdd_total_count": 36, "sdd_functional_count": 37,
    "other_fridge_total_count": 38, "other_fridge_functional_count": 39,
    "stockout_last_3_months": 40,
    "vaccines_out_of_stock_at_visit": 42,
    "vvm_stage_3_4_present": 43,
    "recapping_syringes": 55,
    "safety_box_disposal": 56,
    "non_touch_technique": 57,
    "svc_with_ice_pack": 58,
    "skillful_administration": 59,
    "aefi_history_asked": 60, "aefi_reporting_known": 61, "aefi_info_given": 62,
    "defaulter_list_updated": 65,
    "supervisor_visited_last_month": 68,
    "safety_boxes_used": 80,
    "disinfectants_available": 82,
    "color_coded_bins": 83,
    "tally_sheet_used": 89,
    "epi_card_issued": 90,
    "qr_code_used": 91,
    "neir_data_entry": 92,
    "records_organized": 95,
    "vpd_focal_assigned": 97,
    "vpd_focal_trained": 98,
    "weekly_vpd_booklet_available": 100,
    "cifs_available": 102,
    "tablet_provided": 103,
    "digital_vpd_reporting": 104,
    "score_service_functionality": 133,
    "score_monitoring_system_quality": 134,
    "score_operations_quality": 135,
    "score_practices_knowledge": 136,
}

SUPERVISORY_YES_NO_FIELDS = [
    "fixed_site_open", "signboard_displayed", "charts_displayed", "charts_updated",
    "schedule_displayed", "uc_map_displayed", "room_spacious", "privacy_area",
    "backup_power_available", "backup_power_operational", "microplan_available_with_vaccinator",
    "vaccine_carrier_standard", "zero_dose_list_used", "uc_microplan_copy_at_center",
    "stockout_last_3_months", "vaccines_out_of_stock_at_visit", "vvm_stage_3_4_present",
    "recapping_syringes", "safety_box_disposal", "non_touch_technique", "svc_with_ice_pack",
    "skillful_administration", "aefi_history_asked", "aefi_reporting_known", "aefi_info_given",
    "defaulter_list_updated", "supervisor_visited_last_month", "safety_boxes_used",
    "disinfectants_available", "color_coded_bins", "tally_sheet_used", "epi_card_issued",
    "qr_code_used", "neir_data_entry", "records_organized", "vpd_focal_assigned",
    "vpd_focal_trained", "weekly_vpd_booklet_available", "cifs_available", "tablet_provided",
    "digital_vpd_reporting",
]

SUPERVISORY_SCORE_FIELDS = [
    "score_service_functionality", "score_monitoring_system_quality",
    "score_operations_quality", "score_practices_knowledge",
]


def _parse_pct(v):
    if pd.isna(v):
        return None
    try:
        return float(str(v).strip().rstrip("%"))
    except ValueError:
        return None


def _yes_no_bool(v):
    """True/False for Yes/No, None for 'Not Applicable' or unanswered --
    keeping 'not applicable' out of both the numerator and denominator of any
    Yes-rate calculation, same principle as RCA's is_penta1_assessed."""
    if pd.isna(v):
        return None
    val = str(v).strip().lower()
    if val == "yes":
        return True
    if val == "no":
        return False
    return None  # "Not Applicable" or any other free-text answer


def clean_supervisory(raw_df: pd.DataFrame, period_id: str, log) -> pd.DataFrame:
    if raw_df.shape[1] != SUPERVISORY_COL_COUNT:
        raise ValueError(
            f"Supervisory Checklist file has {raw_df.shape[1]} columns, expected "
            f"{SUPERVISORY_COL_COUNT}. The source layout may have changed -- check "
            f"src/pipeline/clean_monitoring.py's SUPERVISORY_FIELD_INDEX."
        )
    df = pd.DataFrame(index=raw_df.index)
    for field, idx in SUPERVISORY_FIELD_INDEX.items():
        df[field] = raw_df.iloc[:, idx]

    df["visit_datetime"] = pd.to_datetime(df["visit_datetime"], errors="coerce", format="mixed")

    for field in SUPERVISORY_YES_NO_FIELDS:
        df[field] = df[field].apply(_yes_no_bool)
    for field in SUPERVISORY_SCORE_FIELDS:
        df[field] = df[field].apply(_parse_pct)

    for count_field in ["ilr_functional_count", "sdd_total_count", "sdd_functional_count",
                         "other_fridge_total_count", "other_fridge_functional_count"]:
        df[count_field] = pd.to_numeric(df[count_field], errors="coerce")

    df["period_id"] = period_id
    return df
