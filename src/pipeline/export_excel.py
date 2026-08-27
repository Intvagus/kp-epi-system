"""Multi-sheet Excel export of whatever processed data exists for a run.

Coverage and VPD are each independent -- a sheet only gets added for a
component that actually processed, never an empty or broken one for a
component that wasn't uploaded. Reads the SAME data/processed/* files the
dashboard reads and never recomputes anything, so the two can never disagree
(same rule as the bulletin -- see src/bulletin/build.py).

"""
import json
from pathlib import Path

import pandas as pd


def _coverage_district_frame(processed_dir: Path) -> pd.DataFrame | None:
    path = processed_dir / "coverage_district.parquet"
    return pd.read_parquet(path) if path.exists() else None


def _coverage_uc_frame(processed_dir: Path) -> pd.DataFrame | None:
    path = processed_dir / "coverage_uc.parquet"
    return pd.read_parquet(path) if path.exists() else None


def _coverage_summary(processed_dir: Path) -> dict | None:
    path = processed_dir / "coverage_summary.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        summary = json.load(f)
    return summary if summary.get("status") == "ok" else None


def _coverage_kpi_rows(summary: dict) -> list[dict]:
    rows = []
    for kind, period in summary["periods"].items():
        if period.get("status") != "ok":
            continue
        exe = period["executive"]
        dc = exe["district_compliance"]
        rows.append({
            "period_kind": kind, "period_label": exe["current_period_label"],
            "fic_pct": exe["fic_pct"], "dropout_pct": exe["dropout_pct"],
            "target_surviving_infants": exe["target_surviving_infants"],
            "best_antigen": exe["best_antigen"]["antigen"] if exe["best_antigen"] else None,
            "best_antigen_pct": exe["best_antigen"]["pct"] if exe["best_antigen"] else None,
            "worst_antigen": exe["worst_antigen"]["antigen"] if exe["worst_antigen"] else None,
            "worst_antigen_pct": exe["worst_antigen"]["pct"] if exe["worst_antigen"] else None,
            "best_district": exe["best_district"]["district"] if exe["best_district"] else None,
            "best_district_pct": exe["best_district"]["pct"] if exe["best_district"] else None,
            "worst_district": exe["worst_district"]["district"] if exe["worst_district"] else None,
            "worst_district_pct": exe["worst_district"]["pct"] if exe["worst_district"] else None,
            "districts_achieving_target": dc["good"],
            "districts_requiring_intervention": dc["warning"] + dc["poor"],
            "districts_total": dc["total_with_data"],
        })
    return rows


def _coverage_antigen_rows(summary: dict) -> list[dict]:
    rows = []
    for kind, period in summary["periods"].items():
        if period.get("status") != "ok":
            continue
        for a in period["antigen_analysis"]:
            rows.append({"period_kind": kind, **a})
    return rows


def _vpd_summary(processed_dir: Path) -> dict | None:
    path = processed_dir / "vpd_summary.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _vpd_summary_rows(vpd: dict) -> list[dict]:
    return [
        {"metric": "Latest epi week", "value": vpd.get("latest_epi_week")},
        {"metric": "MSL suspected (YTD)", "value": vpd["msl"]["suspected_ytd"]},
        {"metric": "MSL suspected (latest week)", "value": vpd["msl"]["suspected_latest_week"]},
        {"metric": "MSL sample collection rate %", "value": vpd["msl"]["sample_collection_rate_pct"]},
        {"metric": "MSL sample adequacy rate %", "value": vpd["msl"]["sample_adequacy_rate_pct"]},
        {"metric": "Diphtheria cases (YTD)", "value": vpd["diphtheria"]["ytd"]["case_count"]},
        {"metric": "Diphtheria districts affected", "value": vpd["diphtheria"]["ytd"]["districts_affected"]},
        {"metric": "Diphtheria lab confirmed", "value": vpd["diphtheria"]["ytd"]["lab_confirmed_count"]},
        {"metric": "Diphtheria deaths", "value": vpd["diphtheria"]["ytd"]["deaths"]},
        {"metric": "NNT cases (YTD)", "value": vpd["nnt"]["ytd"]["case_count"]},
        {"metric": "NNT deaths", "value": vpd["nnt"]["ytd"]["deaths"]},
    ]


def _vpd_district_rows(vpd: dict) -> list[dict]:
    rows = []
    for r in vpd["msl"]["district_breakdown"]:
        rows.append({"disease": "Measles-Rubella", **r})
    for r in vpd["pertussis"]["district_breakdown"]:
        rows.append({"disease": "Pertussis", **r})
    for r in vpd["nnt"]["by_district_ytd"]:
        rows.append({"disease": "NNT", **r})
    return rows


def _monitoring_summary(processed_dir: Path) -> dict | None:
    path = processed_dir / "monitoring_summary.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _rca_summary_rows(rca: dict) -> list[dict]:
    ov = rca["overview"]
    zd = rca["zero_dose"]
    return [
        {"metric": "Reporting window", "value": rca["reporting_window"]},
        {"metric": "Total children assessed", "value": ov["total_children_assessed"]},
        {"metric": "Total RCA visits", "value": ov["total_rca_visits"]},
        {"metric": "Districts covered", "value": ov["districts_covered"]},
        {"metric": "Zero-dose children (Penta1 not received)", "value": zd["zero_dose_count"]},
        {"metric": "Zero-dose %", "value": zd["zero_dose_pct"]},
    ]


def _supervisory_summary_rows(sup: dict) -> list[dict]:
    ov = sup["overview"]
    rows = [
        {"metric": "Reporting window", "value": sup["reporting_window"]},
        {"metric": "Total supervisory visits", "value": ov["total_visits"]},
        {"metric": "Districts covered", "value": ov["districts_covered"]},
        {"metric": "Facilities covered", "value": ov["facilities_covered"]},
        {"metric": "Fixed-site-open rate %", "value": sup["fixed_site_open_rate"]["pct"]},
    ]
    for s in sup["composite_scores"]:
        rows.append({"metric": f"{s['category']} (avg %)", "value": s["avg_pct"]})
    return rows


def build_processed_excel(processed_dir: Path, output_path: Path) -> Path | None:
    """Writes one .xlsx with a sheet per available, actually-processed
    component. Returns None (writes nothing) if no processed data exists at
    all -- there being nothing to export yet is not an error."""
    sheets: dict[str, pd.DataFrame] = {}

    district_df = _coverage_district_frame(processed_dir)
    if district_df is not None and not district_df.empty:
        sheets["Coverage District Data"] = district_df
        uc_df = _coverage_uc_frame(processed_dir)
        if uc_df is not None and not uc_df.empty:
            sheets["Coverage UC Data"] = uc_df
        coverage_summary = _coverage_summary(processed_dir)
        if coverage_summary:
            kpi_rows = _coverage_kpi_rows(coverage_summary)
            if kpi_rows:
                sheets["Coverage KPI Summary"] = pd.DataFrame(kpi_rows)
            antigen_rows = _coverage_antigen_rows(coverage_summary)
            if antigen_rows:
                sheets["Coverage Antigen Summary"] = pd.DataFrame(antigen_rows)

    vpd = _vpd_summary(processed_dir)
    if vpd:
        sheets["VPD Surveillance Summary"] = pd.DataFrame(_vpd_summary_rows(vpd))
        district_rows = _vpd_district_rows(vpd)
        if district_rows:
            sheets["VPD District Breakdown"] = pd.DataFrame(district_rows)

    monitoring = _monitoring_summary(processed_dir)
    if monitoring:
        rca = monitoring.get("rca", {})
        if rca.get("status") == "ok":
            sheets["RCA Summary"] = pd.DataFrame(_rca_summary_rows(rca))
            sheets["RCA Antigen Coverage"] = pd.DataFrame(rca["antigen_coverage"])
            if rca["district_breakdown"]:
                sheets["RCA District Breakdown"] = pd.DataFrame(rca["district_breakdown"])
        sup = monitoring.get("supervisory", {})
        if sup.get("status") == "ok":
            sheets["Supervisory Summary"] = pd.DataFrame(_supervisory_summary_rows(sup))
            sheets["Supervisory Compliance Items"] = pd.DataFrame(sup["compliance_items"])
            if sup["district_breakdown"]:
                sheets["Supervisory District Breakdown"] = pd.DataFrame(sup["district_breakdown"])

    if not sheets:
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)  # Excel's 31-char sheet-name limit
    return output_path
