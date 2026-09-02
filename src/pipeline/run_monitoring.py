"""Orchestrates the Monitoring domain: load RCA / Supervisory Checklist
files -> clean -> compute indicators -> write data/processed/monitoring_*.
Mirrors run_vpd.py's shape, but the two Monitoring files are independent of
each other (an RCA-only or Supervisory-only upload must still produce a full
summary for whichever one is present) rather than sub-tables of one workbook.
"""
import json
from pathlib import Path

import pandas as pd

from . import indicators_monitoring as ind
from .clean import QualityLog
from .clean_monitoring import clean_rca, clean_supervisory
from .load_monitoring import (
    find_rca_files, find_supervisory_files, load_rca_file, load_supervisory_file,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def _safe_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(lambda v: v if v is None or isinstance(v, str) else str(v))
    return df


def _date_range_label(dates: pd.Series) -> str | None:
    valid = dates.dropna()
    if valid.empty:
        return None
    lo, hi = valid.min(), valid.max()
    if lo.date() == hi.date():
        return lo.strftime("%d %b %Y")
    return f"{lo.strftime('%d %b %Y')} - {hi.strftime('%d %b %Y')}"


def _build_rca_summary(rca: pd.DataFrame) -> dict:
    return {
        "status": "ok",
        "reporting_window": _date_range_label(rca["visit_date"]),
        "overview": ind.rca_overview(rca),
        "monitor_breakdown": ind.rca_monitor_breakdown(rca),
        "antigen_coverage": ind.rca_antigen_coverage(rca),
        "antigen_coverage_by_age_group": ind.rca_antigen_coverage_by_age_group(rca),
        "monitor_remarks": ind.rca_monitor_remarks(rca),
        "zero_dose": ind.rca_zero_dose_summary(rca),
        "district_breakdown": ind.rca_district_breakdown(rca),
        "district_map": ind.rca_district_map(rca),
        "age_group_breakdown": ind.rca_age_group_breakdown(rca),
        "sex_breakdown": ind.rca_sex_breakdown(rca),
        "area_type_breakdown": ind.rca_area_type_breakdown(rca),
        "hard_to_reach": ind.rca_hard_to_reach_summary(rca),
        "high_risk_population": ind.rca_high_risk_summary(rca),
        "vaccine_source_breakdown": ind.rca_vaccine_source_breakdown(rca),
        "non_vaccination_reasons": ind.rca_non_vaccination_reasons(rca),
        "info_source_breakdown": ind.rca_info_source_breakdown(rca),
        "daily_visit_trend": ind.rca_daily_visit_trend(rca),
    }


def _build_supervisory_summary(sup: pd.DataFrame) -> dict:
    return {
        "status": "ok",
        "reporting_window": _date_range_label(sup["visit_datetime"]),
        "overview": ind.supervisory_overview(sup),
        "composite_scores": ind.supervisory_composite_scores(sup),
        "site_type_breakdown": ind.supervisory_site_type_breakdown(sup),
        "site_type_cold_chain": ind.supervisory_site_type_cold_chain(sup),
        "hf_type_breakdown": ind.supervisory_hf_type_breakdown(sup),
        "compliance_items": ind.supervisory_compliance_items(sup),
        "practice_risk_flags": ind.supervisory_practice_risk_flags(sup),
        "cold_chain": ind.supervisory_cold_chain_summary(sup),
        "fixed_site_open_rate": ind.supervisory_fixed_site_open_rate(sup),
        "district_breakdown": ind.supervisory_district_breakdown(sup),
        "district_map": ind.supervisory_district_map(sup),
        "facility_rankings_service_functionality": ind.supervisory_facility_rankings(sup, "score_service_functionality"),
        "facility_rankings_operations_quality": ind.supervisory_facility_rankings(sup, "score_operations_quality"),
        "daily_visit_trend": ind.supervisory_daily_visit_trend(sup),
        "monitor_remarks": ind.supervisory_monitor_remarks(sup),
    }


RCA_AWAITING_STUB = {
    "status": "awaiting_data",
    "message": "No RCA (Rapid Convenience Assessment) file was uploaded for this run.",
}
SUPERVISORY_AWAITING_STUB = {
    "status": "awaiting_data",
    "message": "No Supervisory Checklist file was uploaded for this run.",
}


def run_monitoring(raw_dir: Path | None = None, processed_dir: Path | None = None):
    """`raw_dir`/`processed_dir` default to this project's data/raw and
    data/processed; the web app passes per-job temp directories instead.
    RCA and Supervisory Checklist are independent -- either, both, or
    neither may be present; only what's found gets processed. Returns None
    if neither file was found (nothing to do), otherwise the summary dict
    that was also written to monitoring_summary.json."""
    processed_dir = processed_dir or PROCESSED_DIR
    print("\nMonitoring pipeline starting...")
    processed_dir.mkdir(parents=True, exist_ok=True)
    log = QualityLog()

    rca_files = find_rca_files(raw_dir)
    supervisory_files = find_supervisory_files(raw_dir)
    if not rca_files and not supervisory_files:
        print("  No RCA or Supervisory Checklist file found. Skipping.")
        return None

    summary = {"rca": RCA_AWAITING_STUB, "supervisory": SUPERVISORY_AWAITING_STUB}

    if rca_files:
        frames = [clean_rca(load_rca_file(p), p.stem, log) for p in rca_files]
        rca = pd.concat(frames, ignore_index=True)
        _safe_for_parquet(rca).to_parquet(processed_dir / "monitoring_rca_cases.parquet", index=False)
        print(f"  monitoring_rca_cases.parquet:        {len(rca)} rows")
        summary["rca"] = _build_rca_summary(rca)

    if supervisory_files:
        frames = [clean_supervisory(load_supervisory_file(p), p.stem, log) for p in supervisory_files]
        sup = pd.concat(frames, ignore_index=True)
        _safe_for_parquet(sup).to_parquet(processed_dir / "monitoring_supervisory_visits.parquet", index=False)
        print(f"  monitoring_supervisory_visits.parquet: {len(sup)} rows")
        summary["supervisory"] = _build_supervisory_summary(sup)

    with open(processed_dir / "monitoring_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    flags_df = pd.DataFrame(log.flags)
    if not flags_df.empty:
        flags_df.to_csv(processed_dir / "monitoring_quality_flags.csv", index=False)

    print("Monitoring pipeline finished OK.")
    return summary


if __name__ == "__main__":
    run_monitoring()
