"""Builds a single self-contained output/dashboard.html.

Reads ONLY data/processed/* -- never touches data/raw/ and never recomputes
an indicator. Chart.js is inlined from src/dashboard/chart.umd.min.js (no
CDN) so the file works fully offline and can be emailed as one attachment.
"""
import json
from pathlib import Path

import pandas as pd

from src.pipeline.config import (
    COVERAGE_GOOD,
    COVERAGE_WARNING,
    DROPOUT_GOOD,
    DROPOUT_WARNING,
    OUTLIER_PCT_THRESHOLD,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = Path(__file__).resolve().parent

VPD_AWAITING_STUB = {
    "status": "awaiting_data",
    "latest_epi_week": None,
    "msl": {"suspected_ytd": 0, "suspected_latest_week": 0, "classification_breakdown": {},
            "sample_collection_rate_pct": None, "sample_adequacy_rate_pct": None,
            "dose_status_suspected": {}, "dose_status_confirmed_measles": {},
            "dose_status_confirmed_rubella": {}, "age_distribution": {}, "district_breakdown": [],
            "weekly_trend": []},
    "diphtheria": {"ytd": {"case_count": 0, "districts_affected": 0, "lab_confirmed_count": 0,
                            "pct_no_dpt_history": None, "pct_aged_5_plus": None, "deaths": 0},
                   "weekly_trend": []},
    "pertussis": {"district_breakdown": []},
    "nnt": {"ytd": {"case_count": 0, "deaths": 0}, "by_district_ytd": []},
    "afp": {"status": "awaiting_data", "message": "No VPD surveillance file was uploaded for this run."},
}

UC_FIELDS = [
    "district", "tehsil", "uc_code", "uc_name", "period_id",
    "bcg_pct", "penta1_pct", "penta2_pct", "penta3_pct", "ipv1_pct", "ipv2_pct",
    "mr1_pct", "fic_pct", "tcv_pct", "dropout_pct",
    # UC-level-only antigens (no raw count/target at District/Tehsil level in
    # the source file -- see CLAUDE.md and the Service Delivery tab's
    # "Additional Antigens (Union Council Level Only)" section).
    "opv0_pct", "opv1_pct", "opv2_pct", "opv3_pct", "pcv1_pct", "pcv2_pct", "pcv3_pct",
    "rota1_pct", "rota2_pct",
    "access_rating", "utilisation_rating", "category",
    "is_zero_target", "is_outlier", "is_negative_dropout", "is_consistency_fail",
    "consistency_fail_count",
    "rag_bcg_pct", "rag_penta1_pct", "rag_penta3_pct", "rag_mr1_pct", "rag_fic_pct",
    "rag_dropout_pct",
]

TEHSIL_FIELDS = [
    "district", "tehsil", "period_id",
    "bcg_pct_reported", "penta1_pct_reported", "penta2_pct_reported", "penta3_pct_reported",
    "ipv1_pct_reported", "ipv2_pct_reported", "mr1_pct_reported", "fic_pct_reported",
    "tcv_pct_reported", "dropout_pct_reported",
    "access_rating", "utilisation_rating", "category",
    "cat1_count", "cat2_count", "cat3_count", "cat4_count", "total_ucs",
    "is_negative_dropout",
    "rag_bcg_pct_reported", "rag_penta1_pct_reported", "rag_penta3_pct_reported",
    "rag_mr1_pct_reported", "rag_fic_pct_reported", "rag_dropout_pct_reported",
]

DISTRICT_FIELDS = [
    "district", "period_id", "period_type", "period_label", "is_province_total", "s_no",
    "target_bcg", "target_surviving_infants",
    "bcg_n", "bcg_pct_reported", "penta1_n", "penta1_pct_reported",
    "penta2_n", "penta2_pct_reported", "penta3_n", "penta3_pct_reported",
    "ipv1_n", "ipv1_pct_reported", "ipv2_n", "ipv2_pct_reported",
    "mr1_n", "mr1_pct_reported", "tcv_n", "tcv_pct_reported", "fic_n", "fic_pct_reported",
    "dropout_pct_reported", "access_rating", "utilisation_rating", "category",
    "cat1_count", "cat2_count", "cat3_count", "cat4_count", "total_ucs",
    "is_negative_dropout",
    "rag_bcg_pct_reported", "rag_penta1_pct_reported", "rag_penta2_pct_reported",
    "rag_penta3_pct_reported", "rag_ipv1_pct_reported", "rag_ipv2_pct_reported",
    "rag_mr1_pct_reported", "rag_fic_pct_reported", "rag_tcv_pct_reported",
    "rag_dropout_pct_reported",
]


def _clean_records(records: list[dict], decimals: int = 1) -> list[dict]:
    """Round floats and turn every NaN into None. NaN is a `float` instance in
    Python, including inside object-dtype columns (e.g. a CSV's blank
    'detail' cells) -- json.dumps happily emits the literal `NaN` for it,
    which is NOT valid JSON and breaks JSON.parse in the browser. Every
    record list going into the payload must pass through this."""
    for r in records:
        for k, v in r.items():
            if isinstance(v, float):
                r[k] = None if pd.isna(v) else round(v, decimals)
    return records


def _load_table(processed_dir: Path, name: str, fields: list[str]) -> list[dict]:
    df = pd.read_parquet(processed_dir / name)[fields]
    return _clean_records(df.to_dict(orient="records"))


def _load_csv(processed_dir: Path, name: str) -> list[dict]:
    path = processed_dir / name
    if not path.exists():
        return []
    return _clean_records(pd.read_csv(path).to_dict(orient="records"))


COVERAGE_EMPTY_REPORT = {
    "periods": [], "row_counts": {"district": 0, "tehsil": 0, "uc": 0},
    "exclusions_total": 0, "flags_total": 0, "flags_by_type": {}, "exclusions_by_reason": {},
}


def build_payload(processed_dir: Path) -> dict:
    # Coverage is optional, same principle as VPD/supervision below: a job
    # that only uploaded a VPD line list (no coverage workbook) must still
    # get a working dashboard, with the Coverage tab showing an explicit
    # "awaiting data" state instead of the whole build failing.
    coverage_available = (processed_dir / "coverage_district.parquet").exists()
    if coverage_available:
        district = _load_table(processed_dir, "coverage_district.parquet", DISTRICT_FIELDS)
        tehsil = _load_table(processed_dir, "coverage_tehsil.parquet", TEHSIL_FIELDS)
        uc = _load_table(processed_dir, "coverage_uc.parquet", UC_FIELDS)
        periods = sorted(
            {(d["period_id"], d["period_type"], d["period_label"]) for d in district},
            key=lambda p: p[0],
        )
        # Prefer the latest monthly period as the default view; fall back to
        # the latest period of any type if no monthly period is present.
        monthly = [p for p in periods if p[1] == "monthly"]
        default_period_id = (monthly[-1] if monthly else periods[-1])[0]
        with open(processed_dir / "data_quality_report.json", encoding="utf-8") as f:
            coverage_report = json.load(f)
        coverage_summary_path = processed_dir / "coverage_summary.json"
        if coverage_summary_path.exists():
            with open(coverage_summary_path, encoding="utf-8") as f:
                coverage_summary = json.load(f)
        else:
            coverage_summary = {"status": "no_data"}
    else:
        district, tehsil, uc = [], [], []
        periods = []
        default_period_id = None
        coverage_report = COVERAGE_EMPTY_REPORT
        coverage_summary = {"status": "no_data"}

    vpd_summary_path = processed_dir / "vpd_summary.json"
    if vpd_summary_path.exists():
        with open(vpd_summary_path, encoding="utf-8") as f:
            vpd = json.load(f)
    else:
        vpd = VPD_AWAITING_STUB

    vpd_indicator_summary_path = processed_dir / "vpd_indicator_summary.json"
    if vpd_indicator_summary_path.exists():
        with open(vpd_indicator_summary_path, encoding="utf-8") as f:
            vpd_key_indicators = json.load(f)
    else:
        vpd_key_indicators = {
            "status": "awaiting_data",
            "message": "No Measles Indicator Sheet has been uploaded yet.",
        }

    monitoring_summary_path = processed_dir / "monitoring_summary.json"
    if monitoring_summary_path.exists():
        with open(monitoring_summary_path, encoding="utf-8") as f:
            monitoring = json.load(f)
    else:
        monitoring = {
            "rca": {"status": "awaiting_data", "message": (
                "No RCA (Rapid Convenience Assessment) file has been received yet."
            )},
            "supervisory": {"status": "awaiting_data", "message": (
                "No Supervisory Checklist file has been received yet."
            )},
        }

    who_activities_path = processed_dir / "who_activities_summary.json"
    if who_activities_path.exists():
        with open(who_activities_path, encoding="utf-8") as f:
            who_activities = json.load(f)
    else:
        who_activities = {
            "status": "awaiting_data",
            "message": "No WHO Supported Activities workbook has been uploaded yet.",
        }

    admin_activities_path = processed_dir / "admin_activities_summary.json"
    if admin_activities_path.exists():
        with open(admin_activities_path, encoding="utf-8") as f:
            admin_activities = json.load(f)
    else:
        admin_activities = {
            "status": "awaiting_data",
            "message": "No Admin Activities checklist has been uploaded yet.",
        }

    return {
        "config": {
            "coverage_good": COVERAGE_GOOD,
            "coverage_warning": COVERAGE_WARNING,
            "dropout_good": DROPOUT_GOOD,
            "dropout_warning": DROPOUT_WARNING,
            "outlier_pct_threshold": OUTLIER_PCT_THRESHOLD,
        },
        "periods": [{"period_id": p[0], "period_type": p[1], "label": p[2]} for p in periods],
        "default_period_id": default_period_id,
        "coverage": {
            "district": district,
            "tehsil": tehsil,
            "uc": uc,
        },
        "coverage_available": coverage_available,
        "coverage_summary": coverage_summary,
        "quality": {
            "coverage_report": coverage_report,
            "coverage_flags": _load_csv(processed_dir, "quality_flags.csv"),
            "coverage_exclusions": _load_csv(processed_dir, "exclusions_log.csv"),
            "vpd_flags": _load_csv(processed_dir, "vpd_quality_flags.csv"),
        },
        "vpd": vpd,
        "vpd_key_indicators": vpd_key_indicators,
        "monitoring": monitoring,
        "who_activities": who_activities,
        "admin_activities": admin_activities,
    }


def build(processed_dir: Path | None = None, output_path: Path | None = None):
    """`processed_dir`/`output_path` default to this project's data/processed
    and output/dashboard.html; the web app passes per-job temp paths instead."""
    processed_dir = processed_dir or (PROJECT_ROOT / "data" / "processed")
    output_path = output_path or (PROJECT_ROOT / "output" / "dashboard.html")

    print("Building dashboard...")
    # Coverage, VPD, and Monitoring are each optional (see build_payload) --
    # a dashboard with none of them is the one real error case, since there
    # would be nothing to show at all.
    has_coverage = (processed_dir / "coverage_district.parquet").exists()
    has_vpd = (processed_dir / "vpd_summary.json").exists()
    has_monitoring = (processed_dir / "monitoring_summary.json").exists()
    has_indicator_sheet = (processed_dir / "vpd_indicator_summary.json").exists()
    has_who_activities = (processed_dir / "who_activities_summary.json").exists()
    has_admin_activities = (processed_dir / "admin_activities_summary.json").exists()
    if not has_coverage and not has_vpd and not has_monitoring and not has_indicator_sheet and not has_who_activities and not has_admin_activities:
        raise SystemExit(
            f"No processed data found in {processed_dir}. Run the coverage, VPD, monitoring, "
            f"indicator-sheet, WHO Supported Activities, and/or Admin Activities pipeline first "
            f"to generate at least one dataset before building the dashboard."
        )

    payload = build_payload(processed_dir)
    payload_json = json.dumps(payload, default=str, separators=(",", ":"))
    print(f"  Data payload: {len(payload_json) / 1024:.0f} KB "
          f"({len(payload['coverage']['uc'])} UC rows, "
          f"{len(payload['quality']['coverage_flags'])} quality flags)")

    chartjs_source = (DASHBOARD_DIR / "chart.umd.min.js").read_text(encoding="utf-8")
    # PPTX export ("Download PPT", alongside the existing client-side
    # "Download PDF"): PptxGenJS's own standalone browser bundle (includes
    # JSZip inlined, no other runtime dependency), fetched once via npm
    # (registry.npmjs.org) and checked into the repo -- same "never fetched
    # at build or view time" rule as Chart.js and the district boundaries.
    pptxgenjs_source = (DASHBOARD_DIR / "pptxgen.bundle.js").read_text(encoding="utf-8")
    # District/ADM2 boundaries for the Coverage/Monitoring choropleth maps.
    # Traced from the user-provided reference map (KP_MAP_1.pptx) rather than
    # the earlier geoBoundaries.org set, since it's a real per-district
    # polygon for every current sub-split (Chitral, Kohistan, Kurram, South
    # Waziristan) instead of one shared older boundary -- see
    # config.DISTRICT_TO_BOUNDARY for the district-name mapping and the one
    # flagged naming assumption. Checked into the repo, never fetched at
    # build or view time, so the dashboard stays fully offline.
    kp_geojson = (DASHBOARD_DIR / "kp_districts.geojson").read_text(encoding="utf-8")
    template = (DASHBOARD_DIR / "template.html").read_text(encoding="utf-8")

    html = (
        template
        .replace("/*__CHARTJS_SOURCE__*/", chartjs_source)
        .replace("/*__PPTXGENJS_SOURCE__*/", pptxgenjs_source)
        .replace("/*__EPI_DATA_JSON__*/", payload_json)
        .replace("/*__KP_GEOJSON__*/", kp_geojson)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  Wrote {output_path} ({size_mb:.2f} MB)")
    print("Dashboard build finished OK.")
    return output_path


if __name__ == "__main__":
    build()
