"""Orchestrates the VPD surveillance domain: load line lists -> clean -> compute
indicators -> write data/processed/vpd_*. Separate from run.py (coverage
domain) because the source files, period model (weekly cumulative-to-date vs.
monthly/annual), and indicator set are entirely different -- but both are
called from run_weekly.py so a non-technical user still runs one command.
"""
import json
import sys
from pathlib import Path

import pandas as pd

from . import indicators_vpd as ind
from .clean import QualityLog
from .clean_vpd import clean_diphtheria, clean_msl, clean_nnt, clean_pertussis
from .config import infer_vpd_period
from .load_vpd import find_vpd_files, load_vpd_workbook

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"  # default path; tests and run_vpd() both use this unless overridden


def _safe_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    """Several raw source columns (e.g. doses_received: int values mixed with
    the literal string 'unknown') are genuinely mixed-type -- that's the real
    data, not a bug, and every derived indicator already reads the clean
    columns (dose_status, etc.), not these. Stringify remaining mixed-type
    object columns so parquet can be written at all, without touching any
    column pandas already resolved to a single dtype."""
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(lambda v: v if v is None or isinstance(v, str) else str(v))
    return df

AFP_STUB = {
    "status": "awaiting_data",
    "message": (
        "No AFP (Acute Flaccid Paralysis) line list has been received yet. "
        "This section will populate automatically once one is added to data/raw/ "
        "-- see CLAUDE.md 'Confirmed VPD decisions'."
    ),
}

DEFAULT_KEY_MESSAGES_PATH = PROJECT_ROOT / "data" / "bulletin_inputs" / "key_messages.json"


def _load_key_messages(path: Path) -> list[str]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("messages", [])


def build_bulletin_section(msl: pd.DataFrame, diphtheria: pd.DataFrame,
                            pertussis: pd.DataFrame, nnt: pd.DataFrame,
                            week: int, year: int, key_messages_path: Path) -> dict:
    """Everything the Part 3 bulletin needs for one specific epi week,
    computed once here from the same cleaned case tables and indicator
    functions the dashboard uses -- the bulletin template only reads this,
    never recomputes. 'This week' = exactly that epi_week; 'cumulative' =
    every row with epi_week <= week (so a Week 30 bulletin doesn't include
    weeks 31-32 even though they're present in a later-dated source file)."""
    msl_wk = msl[msl["epi_week"] == week]
    msl_cum = msl[msl["epi_week"] <= week]
    diph_wk = diphtheria[diphtheria["epi_week"] == week]
    diph_cum = diphtheria[diphtheria["epi_week"] <= week]
    pert_cum = pertussis[pertussis["epi_week"] <= week]
    nnt_wk = nnt[nnt["epi_week"] == week]
    nnt_cum = nnt[nnt["epi_week"] <= week]

    eligible_wk = msl_wk[msl_wk["is_eligible_age"]]
    pct_zero_dose_eligible = (
        (eligible_wk["dose_status"] == "Zero dose").sum() / len(eligible_wk) * 100
        if len(eligible_wk) else None
    )

    return {
        "epi_week": week,
        "year": year,
        "week_label": f"Week {week}, {year}",
        "cumulative_label": f"Week 1-{week},{year}",
        "msl": {
            "suspected_this_week": int(len(msl_wk)),
            "measles_confirmed_this_week": int(msl_wk["is_confirmed_measles"].sum()),
            "rubella_confirmed_this_week": int(msl_wk["is_confirmed_rubella"].sum()),
            "pct_zero_dose_eligible_this_week": pct_zero_dose_eligible,
            "classification_breakdown_this_week": ind.classification_breakdown(msl_wk),
            "dose_status_suspected_this_week": ind.dose_status_breakdown(msl_wk, eligible_only=True),
            "dose_status_confirmed_this_week": ind.dose_status_breakdown(
                msl_wk, confirmed_only=True, disease="any", eligible_only=True),
            "age_distribution_this_week": ind.age_distribution(msl_wk),
            "district_breakdown_this_week": ind.district_breakdown(msl_wk).to_dict(orient="records"),
            "cumulative": {
                "suspected": int(len(msl_cum)),
                "measles_confirmed": int(msl_cum["is_confirmed_measles"].sum()),
                "rubella_confirmed": int(msl_cum["is_confirmed_rubella"].sum()),
                "sample_collection_rate_pct": ind.sample_collection_rate(msl_cum),
            },
            "week_over_week": ind.week_over_week_delta(msl, week),
        },
        "diphtheria": {
            "this_week": ind.diphtheria_summary(diph_wk),
            "cumulative": ind.diphtheria_summary(diph_cum),
            "age_band_counts_cumulative": ind.diphtheria_age_band_counts(diph_cum),
            "week_over_week": ind.week_over_week_delta(diphtheria, week),
        },
        "pertussis": {
            "district_breakdown_cumulative": ind.pertussis_district_counts(pert_cum).to_dict(orient="records"),
            "grand_total_cumulative": int(len(pert_cum)),
        },
        "nnt": {
            "this_week_case_count": int(len(nnt_wk)),
            "this_week_district_breakdown": nnt_wk.groupby("district").size().reset_index(name="case_count").to_dict(orient="records"),
            "cumulative_case_count": int(len(nnt_cum)),
            "cumulative_district_breakdown": nnt_cum.groupby("district").size().reset_index(name="case_count").to_dict(orient="records"),
        },
        "afp": AFP_STUB,
        "key_messages": _load_key_messages(key_messages_path),
    }


def run_vpd(raw_dir: Path | None = None, processed_dir: Path | None = None,
            key_messages_path: Path | None = None):
    """`raw_dir`/`processed_dir` default to this project's data/raw and
    data/processed; the web app passes per-job temp directories instead.
    `key_messages_path` defaults to the repo's hand-edited
    data/bulletin_inputs/key_messages.json -- the web app writes a per-job
    copy instead so each upload can carry its own key messages."""
    processed_dir = processed_dir or PROCESSED_DIR
    key_messages_path = key_messages_path or DEFAULT_KEY_MESSAGES_PATH
    print("\nVPD surveillance pipeline starting...")
    processed_dir.mkdir(parents=True, exist_ok=True)
    log = QualityLog()

    files = find_vpd_files(raw_dir)
    if not files:
        print("  No VPD line list found (filename must contain 'VPD'). Skipping.")
        return None

    msl_frames, diph_frames, pert_frames, nnt_frames = [], [], [], []

    for path in files:
        try:
            period = infer_vpd_period(path.name)
        except ValueError as e:
            raise SystemExit(f"\nFAILED loading {path.name}: {e}") from e

        wb = load_vpd_workbook(path)
        print(f"  Cleaning {path.name} (period {period.period_id})...")
        try:
            msl_frames.append(clean_msl(wb["sheets"]["msl"], period.period_id, log))
            diph_frames.append(clean_diphtheria(wb["sheets"]["diphtheria"], period.period_id, log))
            pert_frames.append(clean_pertussis(wb["sheets"]["pertussis"], period.period_id, log))
            nnt_frames.append(clean_nnt(wb["sheets"]["nnt"], period.period_id, log))
        except (KeyError, ValueError) as e:
            raise SystemExit(
                f"\nFAILED cleaning {path.name}: {e}. The sheet layout may have "
                f"changed -- check src/pipeline/clean_vpd.py's column lists."
            ) from e

    msl = pd.concat(msl_frames, ignore_index=True)
    diphtheria = pd.concat(diph_frames, ignore_index=True)
    pertussis = pd.concat(pert_frames, ignore_index=True)
    nnt = pd.concat(nnt_frames, ignore_index=True)

    print(f"\nWriting processed VPD output to {processed_dir} ...")
    _safe_for_parquet(msl).to_parquet(processed_dir / "vpd_msl_cases.parquet", index=False)
    _safe_for_parquet(diphtheria).to_parquet(processed_dir / "vpd_diphtheria_cases.parquet", index=False)
    _safe_for_parquet(pertussis).to_parquet(processed_dir / "vpd_pertussis_cases.parquet", index=False)
    _safe_for_parquet(nnt).to_parquet(processed_dir / "vpd_nnt_cases.parquet", index=False)
    print(f"  vpd_msl_cases.parquet:         {len(msl)} rows")
    print(f"  vpd_diphtheria_cases.parquet:  {len(diphtheria)} rows")
    print(f"  vpd_pertussis_cases.parquet:   {len(pertussis)} rows")
    print(f"  vpd_nnt_cases.parquet:         {len(nnt)} rows")

    latest_week = int(msl["epi_week"].max())
    summary = {
        "latest_epi_week": latest_week,
        "msl": {
            "suspected_ytd": ind.suspected_case_count(msl),
            "suspected_latest_week": ind.suspected_case_count(msl, latest_week),
            "classification_breakdown": ind.classification_breakdown(msl),
            "sample_collection_rate_pct": ind.sample_collection_rate(msl),
            "sample_adequacy_rate_pct": ind.sample_adequacy_rate(msl),
            "dose_status_suspected": ind.dose_status_breakdown(msl, confirmed_only=False),
            "dose_status_confirmed_measles": ind.dose_status_breakdown(msl, confirmed_only=True, disease="measles"),
            "dose_status_confirmed_rubella": ind.dose_status_breakdown(msl, confirmed_only=True, disease="rubella"),
            "age_distribution": ind.age_distribution(msl),
            "district_breakdown": ind.district_breakdown(msl).to_dict(orient="records"),
            "weekly_trend": ind.msl_weekly_trend(msl).to_dict(orient="records"),
            "reporting_footprint": ind.reporting_footprint(msl),
            "sex_breakdown": ind.sex_breakdown(msl),
            "outcome_breakdown": ind.outcome_breakdown(msl),
            "complications_breakdown": ind.complications_breakdown(msl),
            "top_districts": ind.top_districts_by_cases(msl, 10),
            "daily_epi_curve": ind.daily_epi_curve(msl),
            "data_quality": {
                "duplicate_epid": ind.duplicate_epid_summary(msl),
                "under_age_vaccinated_anomaly": ind.under_eligible_age_vaccinated_anomaly(msl),
                "field_completeness": ind.field_completeness(msl),
                "classification_discordance": ind.classification_discordance_matrix(msl),
                "lab_confirmed_dose_validation": ind.lab_confirmed_dose_validation(msl),
                "timeliness": ind.timeliness_buckets(msl),
            },
            "district_action_priority": ind.district_action_priority(msl),
        },
        "diphtheria": {
            "ytd": ind.diphtheria_summary(diphtheria),
            "latest_week": ind.diphtheria_summary(diphtheria, latest_week),
            "weekly_trend": ind.weekly_case_counts(diphtheria).to_dict(orient="records"),
        },
        "pertussis": {
            # total_cases is len(pertussis) directly, not a sum of
            # district_breakdown -- district_breakdown groups by district,
            # which silently drops the 1 row with a missing/null district
            # (pandas groupby excludes NaN keys), so summing it would
            # undercount the true case total by that row.
            "total_cases": len(pertussis),
            "district_breakdown": ind.pertussis_district_counts(pertussis).to_dict(orient="records"),
            "weekly_trend": ind.weekly_case_counts(pertussis).to_dict(orient="records"),
        },
        "nnt": {
            "ytd": {k: v for k, v in ind.nnt_summary(nnt).items() if k != "by_district"},
            "by_district_ytd": ind.nnt_summary(nnt)["by_district"].to_dict(orient="records"),
            "weekly_trend": ind.weekly_case_counts(nnt).to_dict(orient="records"),
        },
        "afp": AFP_STUB,
    }

    # `period` is whichever raw file was loaded last -- fine while there's
    # only one VPD workbook per run; if multiple ever land in data/raw/ at
    # once, revisit which one should own the bulletin's year.
    bulletin_year = int(period.period_id.split("-")[0])
    summary["bulletin"] = build_bulletin_section(
        msl, diphtheria, pertussis, nnt, latest_week, bulletin_year, key_messages_path
    )

    with open(processed_dir / "vpd_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    flags_df = pd.DataFrame(log.flags)
    if not flags_df.empty:
        flags_df.to_csv(processed_dir / "vpd_quality_flags.csv", index=False)

    print("\nVPD data quality summary:")
    print(f"  {len(log.flags)} rows flagged -- see vpd_quality_flags.csv (all kept in data except "
          f"sheet_subheader_row_dropped, a non-case artifact row removed at cleaning)")
    if not flags_df.empty:
        for flag_type, count in flags_df["flag_type"].value_counts().to_dict().items():
            print(f"    - {flag_type}: {count}")

    print("VPD pipeline finished OK.")
    return summary


if __name__ == "__main__":
    try:
        run_vpd()
    except SystemExit as e:
        print(e, file=sys.stderr)
        sys.exit(1)
