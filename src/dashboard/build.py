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


def build_payload(processed_dir: Path) -> dict:
    district = _load_table(processed_dir, "coverage_district.parquet", DISTRICT_FIELDS)
    periods = sorted(
        {(d["period_id"], d["period_type"], d["period_label"]) for d in district},
        key=lambda p: p[0],
    )
    # Prefer the latest monthly period as the default view; fall back to the
    # latest period of any type if no monthly period is present.
    monthly = [p for p in periods if p[1] == "monthly"]
    default_period_id = (monthly[-1] if monthly else periods[-1])[0]

    with open(processed_dir / "data_quality_report.json", encoding="utf-8") as f:
        coverage_report = json.load(f)
    vpd_summary_path = processed_dir / "vpd_summary.json"
    if vpd_summary_path.exists():
        with open(vpd_summary_path, encoding="utf-8") as f:
            vpd = json.load(f)
    else:
        vpd = VPD_AWAITING_STUB

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
            "tehsil": _load_table(processed_dir, "coverage_tehsil.parquet", TEHSIL_FIELDS),
            "uc": _load_table(processed_dir, "coverage_uc.parquet", UC_FIELDS),
        },
        "quality": {
            "coverage_report": coverage_report,
            "coverage_flags": _load_csv(processed_dir, "quality_flags.csv"),
            "coverage_exclusions": _load_csv(processed_dir, "exclusions_log.csv"),
            "vpd_flags": _load_csv(processed_dir, "vpd_quality_flags.csv"),
        },
        "vpd": vpd,
        "supervision": {
            "status": "awaiting_data",
            "message": (
                "No supervisory-visit data has been received yet. This tab will "
                "populate automatically once a supervisory-visit file is added "
                "to data/raw/ and the schema is confirmed."
            ),
        },
    }


def build(processed_dir: Path | None = None, output_path: Path | None = None):
    """`processed_dir`/`output_path` default to this project's data/processed
    and output/dashboard.html; the web app passes per-job temp paths instead."""
    processed_dir = processed_dir or (PROJECT_ROOT / "data" / "processed")
    output_path = output_path or (PROJECT_ROOT / "output" / "dashboard.html")

    print("Building dashboard...")
    for required in ["coverage_district.parquet", "coverage_tehsil.parquet",
                      "coverage_uc.parquet", "data_quality_report.json"]:
        if not (processed_dir / required).exists():
            raise SystemExit(
                f"Missing {processed_dir / required}. Run the coverage pipeline first "
                f"to generate processed data before building the dashboard."
            )

    payload = build_payload(processed_dir)
    payload_json = json.dumps(payload, default=str, separators=(",", ":"))
    print(f"  Data payload: {len(payload_json) / 1024:.0f} KB "
          f"({len(payload['coverage']['uc'])} UC rows, "
          f"{len(payload['quality']['coverage_flags'])} quality flags)")

    chartjs_source = (DASHBOARD_DIR / "chart.umd.min.js").read_text(encoding="utf-8")
    template = (DASHBOARD_DIR / "template.html").read_text(encoding="utf-8")

    html = (
        template
        .replace("/*__CHARTJS_SOURCE__*/", chartjs_source)
        .replace("/*__EPI_DATA_JSON__*/", payload_json)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  Wrote {output_path} ({size_mb:.2f} MB)")
    print("Dashboard build finished OK.")
    return output_path


if __name__ == "__main__":
    build()
