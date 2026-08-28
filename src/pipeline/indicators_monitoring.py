"""Monitoring domain indicator formulas -- RCA (child-level vaccination-status
spot checks) and Supervisory Checklist (facility-level visit compliance),
one function each, same convention as indicators_vpd.py. The dashboard and
Excel export both read only data/processed/monitoring_summary.json, never
recomputing themselves.
"""
import numpy as np
import pandas as pd

from .config import DISTRICT_TO_BOUNDARY, RCA_VACCINE_ANTIGENS
from .clean_monitoring import RCA_ANTIGEN_FIELD_MAP, SUPERVISORY_YES_NO_FIELDS


def _value_counts_dropna_false(series: pd.Series) -> dict:
    """value_counts(dropna=False) keeps a missing value bucketed (not
    silently dropped from the total), but its key is float('nan') --
    JSON's key-stringification turns that into the literal text "NaN",
    which read as a real category name on the dashboard. Relabelled to a
    human-readable bucket here, once, for every breakdown that needs it."""
    counts = series.value_counts(dropna=False).to_dict()
    if np.nan in counts:
        counts["Not Recorded"] = counts.pop(np.nan)
    return counts


# ---------------------------------------------------------------------------
# RCA (Rapid Convenience Assessment)
# ---------------------------------------------------------------------------

def rca_overview(df: pd.DataFrame) -> dict:
    return {
        "total_children_assessed": int(len(df)),
        "total_rca_visits": int(df["record_id"].nunique()),
        "districts_covered": int(df["district"].nunique()),
        "monitors_involved": int(df["monitor_name"].nunique()),
    }


def rca_monitor_breakdown(df: pd.DataFrame) -> dict:
    """Number of RCA visits (not child rows) per monitor designation and per
    monitor agency -- deduplicated by record_id, since each visit has
    multiple child rows sharing the same monitor."""
    visits = df.drop_duplicates(subset="record_id")
    return {
        "by_designation": _value_counts_dropna_false(visits["monitor_designation"]),
        "by_agency": _value_counts_dropna_false(visits["monitor_agency"]),
    }


def rca_antigen_coverage(df: pd.DataFrame) -> list[dict]:
    """% Vaccinated among children for whom the antigen was applicable
    (Vaccinated + Not Vaccinated), for every antigen in schedule order.
    'Not Applicable'/unassessed rows are excluded from the denominator --
    they were never due for that dose, not a coverage gap."""
    rows = []
    for antigen in RCA_VACCINE_ANTIGENS:
        field = RCA_ANTIGEN_FIELD_MAP[antigen]
        assessed = df[df[field].isin(["Vaccinated", "Not Vaccinated"])]
        vaccinated = int((assessed[field] == "Vaccinated").sum())
        total = len(assessed)
        rows.append({
            "antigen": antigen, "vaccinated": vaccinated, "assessed": total,
            "pct": (vaccinated / total * 100) if total else None,
        })
    return rows


def rca_zero_dose_summary(df: pd.DataFrame) -> dict:
    assessed = df[df["is_penta1_assessed"]]
    zero_dose = assessed[assessed["is_zero_dose"]]
    by_district = (
        zero_dose.groupby("district").size().reset_index(name="zero_dose_count")
        .sort_values("zero_dose_count", ascending=False).to_dict(orient="records")
    )
    return {
        "assessed_count": int(len(assessed)),
        "zero_dose_count": int(len(zero_dose)),
        "zero_dose_pct": (len(zero_dose) / len(assessed) * 100) if len(assessed) else None,
        "by_district": by_district,
    }


def rca_district_breakdown(df: pd.DataFrame) -> list[dict]:
    rows = []
    for district, g in df.groupby("district"):
        assessed = g[g["is_penta1_assessed"]]
        zero_dose = int(assessed["is_zero_dose"].sum())
        rows.append({
            "district": district,
            "children_assessed": int(len(g)),
            "zero_dose_count": zero_dose,
            "zero_dose_pct": (zero_dose / len(assessed) * 100) if len(assessed) else None,
        })
    return sorted(rows, key=lambda r: r["children_assessed"], reverse=True)


def rca_district_map(df: pd.DataFrame) -> dict:
    """Per-boundary-polygon RCA activity for the district choropleth map,
    reusing config.DISTRICT_TO_BOUNDARY (the same mapping the Coverage tab's
    map uses) -- a handful of newer sub-split districts share one older
    boundary polygon, combined here by summing raw counts, never averaging
    percentages, same rule as every other aggregate in this pipeline. Any
    RCA district name not found in that mapping is reported as unmapped
    (flagged, not guessed at) rather than silently dropped from the map."""
    unmapped = sorted(set(df["district"].unique()) - set(DISTRICT_TO_BOUNDARY))
    by_boundary = {}
    for boundary_name in sorted(set(DISTRICT_TO_BOUNDARY.values())):
        component_districts = sorted(d for d, b in DISTRICT_TO_BOUNDARY.items() if b == boundary_name)
        rows = df[df["district"].isin(component_districts)]
        if rows.empty:
            continue
        assessed = rows[rows["is_penta1_assessed"]]
        zero_dose = int(assessed["is_zero_dose"].sum())
        by_boundary[boundary_name] = {
            "component_districts": sorted(rows["district"].unique().tolist()),
            "children_assessed": int(len(rows)),
            "rca_visits": int(rows["record_id"].nunique()),
            "zero_dose_count": zero_dose,
            "zero_dose_pct": (zero_dose / len(assessed) * 100) if len(assessed) else None,
        }
    return {"unmapped_districts": unmapped, "features": by_boundary}


def rca_age_group_breakdown(df: pd.DataFrame) -> dict:
    return df["age_group"].value_counts(dropna=True).to_dict()


def rca_sex_breakdown(df: pd.DataFrame) -> dict:
    return _value_counts_dropna_false(df["sex"])


def rca_area_type_breakdown(df: pd.DataFrame) -> list[dict]:
    """Zero-dose rate by area type (rural/urban) -- surfaces whether
    unreached children cluster in a particular area type."""
    rows = []
    for area_type, g in df.groupby("area_type"):
        assessed = g[g["is_penta1_assessed"]]
        zero_dose = int(assessed["is_zero_dose"].sum())
        rows.append({
            "area_type": area_type, "children_assessed": int(len(g)),
            "zero_dose_pct": (zero_dose / len(assessed) * 100) if len(assessed) else None,
        })
    return rows


def rca_hard_to_reach_summary(df: pd.DataFrame) -> dict:
    hard = df[df["hard_to_reach_area"].astype(str).str.strip().str.lower() == "yes"]
    assessed = hard[hard["is_penta1_assessed"]]
    return {
        "children_in_hard_to_reach": int(len(hard)),
        "zero_dose_pct": (int(assessed["is_zero_dose"].sum()) / len(assessed) * 100) if len(assessed) else None,
    }


def rca_high_risk_summary(df: pd.DataFrame) -> dict:
    risk = df[df["high_risk_population"].astype(str).str.strip().str.lower() == "yes"]
    assessed = risk[risk["is_penta1_assessed"]]
    return {
        "children_in_high_risk_population": int(len(risk)),
        "zero_dose_pct": (int(assessed["is_zero_dose"].sum()) / len(assessed) * 100) if len(assessed) else None,
    }


def rca_vaccine_source_breakdown(df: pd.DataFrame) -> dict:
    """card vs. recall -- a proxy for how verifiable the assessment is
    (card = confirmed against a written record; recall = caregiver memory)."""
    return _value_counts_dropna_false(df["vaccine_source"])


def rca_non_vaccination_reasons(df: pd.DataFrame) -> dict:
    return df["non_vaccination_reason"].dropna().value_counts().to_dict()


def rca_info_source_breakdown(df: pd.DataFrame) -> dict:
    """Social-mobilization channel free text is comma-separated (e.g. 'LHW
    visit, Mosque Miking') -- split and counted per individual channel."""
    counts: dict[str, int] = {}
    for value in df["vaccination_info_source"].dropna():
        for part in str(value).split(","):
            part = part.strip()
            if part:
                counts[part] = counts.get(part, 0) + 1
    return counts


def rca_daily_visit_trend(df: pd.DataFrame) -> list[dict]:
    valid = df[df["visit_date"].notna()]
    if valid.empty:
        return []
    g = valid.groupby(valid["visit_date"].dt.date).size().reset_index(name="children_assessed")
    g["visit_date"] = g["visit_date"].astype(str)
    return g.sort_values("visit_date").to_dict(orient="records")


# ---------------------------------------------------------------------------
# Supervisory Checklist
# ---------------------------------------------------------------------------

def supervisory_overview(df: pd.DataFrame) -> dict:
    return {
        "total_visits": int(len(df)),
        "districts_covered": int(df["district"].nunique()),
        "facilities_covered": int(df["health_facility"].nunique(dropna=True)),
        "monitors_involved": int(df["monitor_name"].nunique(dropna=True)),
    }


SCORE_LABELS = {
    "score_service_functionality": "Service Functionality",
    "score_monitoring_system_quality": "Monitoring System Quality",
    "score_operations_quality": "Operations Quality",
    "score_practices_knowledge": "Practices & Knowledge",
}


def supervisory_composite_scores(df: pd.DataFrame) -> list[dict]:
    """Pass-through of the source system's own 4 composite compliance
    scores per visit (average/min/max across visits) -- not recomputed here,
    same 'trust the sheet' principle as Coverage's UC-level Access/
    Utilisation: the exact question-to-category weighting isn't documented,
    so re-deriving it would mean guessing."""
    rows = []
    for field, label in SCORE_LABELS.items():
        valid = df[field].dropna()
        rows.append({
            "category": label,
            "avg_pct": float(valid.mean()) if len(valid) else None,
            "min_pct": float(valid.min()) if len(valid) else None,
            "max_pct": float(valid.max()) if len(valid) else None,
            "visits_scored": int(len(valid)),
        })
    return rows


def supervisory_site_type_breakdown(df: pd.DataFrame) -> dict:
    return _value_counts_dropna_false(df["site_type"])


def supervisory_hf_type_breakdown(df: pd.DataFrame) -> dict:
    return df["hf_type"].value_counts(dropna=True).to_dict()


def _yes_rate(series: pd.Series) -> dict:
    valid = series.dropna()
    yes = int((valid == True).sum())  # noqa: E712 -- explicit True/False/None tri-state, not truthiness
    return {"yes": yes, "answered": int(len(valid)), "pct": (yes / len(valid) * 100) if len(valid) else None}


COMPLIANCE_ITEM_LABELS = {
    "signboard_displayed": "EPI signboard displayed",
    "charts_updated": "Monitoring charts updated to last month",
    "schedule_displayed": "Updated EPI schedule displayed",
    "uc_map_displayed": "UC map displayed",
    "backup_power_operational": "Backup power operational (where available)",
    "vaccine_carrier_standard": "Standard vaccine carrier (4 cool packs + foam pad)",
    "zero_dose_list_used": "Zero-dose list used to track children",
    "non_touch_technique": "Non-touch technique followed",
    "aefi_reporting_known": "Vaccinator knows AEFI reporting mechanism",
    "defaulter_list_updated": "Updated defaulter list available",
    "tally_sheet_used": "Tally sheet used during vaccination",
    "epi_card_issued": "EPI card issued for every child",
    "neir_data_entry": "Data entered into NEIR/EMR/SEIR",
    "vpd_focal_assigned": "VPD surveillance focal person assigned",
    "weekly_vpd_booklet_available": "Weekly VPD report booklet available",
    "cifs_available": "CIFs (AFP/MR/Diph/Pert/NT) and AEFI forms available",
    "tablet_provided": "Tablet provided for VPD surveillance",
    "digital_vpd_reporting": "Reporting VPD cases digitally",
    "safety_boxes_used": "Safety boxes available and used",
    "disinfectants_available": "Disinfectants/surface cleaning materials available",
    "color_coded_bins": "Color-coded waste bins present",
}


def supervisory_compliance_items(df: pd.DataFrame) -> list[dict]:
    """Yes-rate for a curated set of individually meaningful checklist
    items (site infrastructure, cold chain, injection safety, documentation,
    VPD-readiness, waste management) -- not all 137 raw columns, which
    include free-text/remarks fields and an entirely-unanswered UC-microplan
    block (see run_monitoring.py). Sorted ascending by yes-rate so the
    weakest compliance areas surface first."""
    rows = []
    for field, label in COMPLIANCE_ITEM_LABELS.items():
        rate = _yes_rate(df[field])
        if rate["answered"] == 0:
            continue
        rows.append({"item": label, **rate})
    rows.sort(key=lambda r: (r["pct"] if r["pct"] is not None else 999))
    return rows


PRACTICE_RISK_LABELS = {
    "recapping_syringes": "Vaccinator recapping used syringes (unsafe injection practice)",
}


def supervisory_practice_risk_flags(df: pd.DataFrame) -> list[dict]:
    """Checklist items where a 'Yes' answer is the concerning outcome (the
    opposite polarity of supervisory_compliance_items, where Yes = good) --
    reported separately so a high 'Yes' rate here reads as a risk, not
    lumped into a ranking where low numbers are assumed to be the problem."""
    rows = []
    for field, label in PRACTICE_RISK_LABELS.items():
        rate = _yes_rate(df[field])
        if rate["answered"] == 0:
            continue
        rows.append({"item": label, **rate})
    rows.sort(key=lambda r: (r["pct"] if r["pct"] is not None else -1), reverse=True)
    return rows


def supervisory_cold_chain_summary(df: pd.DataFrame) -> dict:
    """SDD and 'other' refrigerators have both a Total and a Functional
    count in the source, so a functional-ratio is computable; ILR only has a
    Functional count (no Total column in the source export), so it's
    reported as a raw functional-unit count, not a ratio that would need a
    denominator that doesn't exist."""
    def _ratio(total_col, func_col):
        total = df[total_col].sum()
        func = df[func_col].sum()
        # A facility reporting more functional units than its own total is a
        # source data-entry inconsistency (seen in this data) -- flagged and
        # kept, not silently dropped or clipped; the pct can legitimately
        # exceed 100% as a result, so inconsistent_visits tells the UI when
        # to show a caveat instead of just a misleading number.
        inconsistent = int((df[func_col] > df[total_col]).sum())
        return {
            "total_units": int(total) if pd.notna(total) else 0,
            "functional_units": int(func) if pd.notna(func) else 0,
            "pct_functional": (func / total * 100) if total else None,
            "inconsistent_visits": inconsistent,
        }
    return {
        "ilr_functional_units_observed": int(df["ilr_functional_count"].sum()) if df["ilr_functional_count"].notna().any() else 0,
        "sdd": _ratio("sdd_total_count", "sdd_functional_count"),
        "other_refrigerators": _ratio("other_fridge_total_count", "other_fridge_functional_count"),
        "backup_power_available": _yes_rate(df["backup_power_available"]),
        "stockout_last_3_months": _yes_rate(df["stockout_last_3_months"]),
        "vaccines_out_of_stock_at_visit": _yes_rate(df["vaccines_out_of_stock_at_visit"]),
        "vvm_stage_3_4_present": _yes_rate(df["vvm_stage_3_4_present"]),
    }


def supervisory_fixed_site_open_rate(df: pd.DataFrame) -> dict:
    """Denominator is fixed-site visits only -- outreach/mobile visits don't
    have a 'site open' concept."""
    fixed = df[df["site_type"] == "fixed"]
    return _yes_rate(fixed["fixed_site_open"])


def supervisory_district_breakdown(df: pd.DataFrame) -> list[dict]:
    rows = []
    for district, g in df.groupby("district"):
        row = {"district": district, "visits": int(len(g))}
        for field, label in SCORE_LABELS.items():
            valid = g[field].dropna()
            row[field] = float(valid.mean()) if len(valid) else None
        rows.append(row)
    return sorted(rows, key=lambda r: r["visits"], reverse=True)


def supervisory_district_map(df: pd.DataFrame) -> dict:
    """Per-boundary-polygon Supervisory Checklist activity for the district
    choropleth map -- same DISTRICT_TO_BOUNDARY combining/summing rule as
    rca_district_map. Composite scores are averaged (they're already
    percentages, not raw counts, so there's nothing to sum)."""
    unmapped = sorted(set(df["district"].unique()) - set(DISTRICT_TO_BOUNDARY))
    by_boundary = {}
    for boundary_name in sorted(set(DISTRICT_TO_BOUNDARY.values())):
        component_districts = sorted(d for d, b in DISTRICT_TO_BOUNDARY.items() if b == boundary_name)
        rows = df[df["district"].isin(component_districts)]
        if rows.empty:
            continue
        entry = {
            "component_districts": sorted(rows["district"].unique().tolist()),
            "visits": int(len(rows)),
            "facilities": int(rows["health_facility"].nunique(dropna=True)),
        }
        for field, label in SCORE_LABELS.items():
            valid = rows[field].dropna()
            entry[field] = float(valid.mean()) if len(valid) else None
        by_boundary[boundary_name] = entry
    return {"unmapped_districts": unmapped, "features": by_boundary}


def supervisory_facility_rankings(df: pd.DataFrame, score_field: str, n: int = 5) -> dict:
    """Best/worst n visited facilities by one composite score field, for
    facilities visited exactly once (repeat visits to the same facility
    would need to be averaged, but with a single snapshot per facility in
    this data there's nothing to average yet)."""
    scored = df[df["health_facility"].notna() & df[score_field].notna()]
    scored = scored.drop_duplicates(subset="health_facility")
    ranked = scored.sort_values(score_field, ascending=False)
    cols = ["health_facility", "district", score_field]
    return {
        "top": ranked.head(n)[cols].rename(columns={score_field: "pct"}).to_dict(orient="records"),
        "bottom": ranked.tail(n)[cols].rename(columns={score_field: "pct"}).to_dict(orient="records"),
    }


def supervisory_daily_visit_trend(df: pd.DataFrame) -> list[dict]:
    valid = df[df["visit_datetime"].notna()]
    if valid.empty:
        return []
    g = valid.groupby(valid["visit_datetime"].dt.date).size().reset_index(name="visits")
    g["visit_date"] = g["visit_datetime"].astype(str)
    return g[["visit_date", "visits"]].sort_values("visit_date").to_dict(orient="records")
