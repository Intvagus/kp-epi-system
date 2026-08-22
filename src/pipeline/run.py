"""Orchestrates: load raw Excel -> clean -> compute indicators -> write
data/processed/. Run directly (`python -m src.pipeline.run`) or via run_weekly.py.

Fails loudly: any raw file that doesn't match the expected shape raises with a
specific, actionable message rather than a bare stack trace bubbling up.
"""
import json
import sys
import traceback
from pathlib import Path

import pandas as pd

from . import indicators
from .clean import QualityLog, clean_district, clean_tehsil, clean_uc
from .load import load_all_workbooks

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _add_rag_columns(df: pd.DataFrame, pct_col: str, dropout_col: str | None = None):
    df["rag_" + pct_col] = df[pct_col].apply(indicators.coverage_rag)
    if dropout_col:
        df["rag_" + dropout_col] = df[dropout_col].apply(indicators.dropout_rag)
    return df


def run(raw_dir: Path | None = None, processed_dir: Path | None = None):
    """`raw_dir`/`processed_dir` default to this project's data/raw and
    data/processed (the CLI path); the web app passes per-job temp
    directories instead so concurrent uploads stay isolated."""
    processed_dir = processed_dir or (PROJECT_ROOT / "data" / "processed")
    print("EPI pipeline starting...")
    processed_dir.mkdir(parents=True, exist_ok=True)
    log = QualityLog()

    try:
        workbooks = load_all_workbooks(raw_dir)
    except Exception as e:
        print(f"\nFAILED while loading raw Excel files: {e}", file=sys.stderr)
        raise SystemExit(1) from e

    district_frames, tehsil_frames, uc_frames = [], [], []

    for wb in workbooks:
        period = wb["period"]
        print(f"\nCleaning {wb['path'].name} (period {period.period_id})...")
        try:
            d = clean_district(wb["sheets"]["district"], period.period_id, log)
            d["period_type"], d["period_label"] = period.period_type, period.label
            district_frames.append(d)

            t = clean_tehsil(wb["sheets"]["tehsil"], period.period_id, log)
            t["period_type"], t["period_label"] = period.period_type, period.label
            tehsil_frames.append(t)

            u = clean_uc(wb["sheets"]["uc_coverages"], wb["sheets"]["uc_difference"],
                         period.period_id, log)
            u["period_type"], u["period_label"] = period.period_type, period.label
            uc_frames.append(u)
        except KeyError as e:
            raise SystemExit(
                f"\nFAILED cleaning {wb['path'].name}: expected column {e} not found. "
                f"The sheet layout may have changed -- check src/pipeline/clean.py's "
                f"rename maps against the actual column headers in this file."
            ) from e

    district_all = pd.concat(district_frames, ignore_index=True)
    tehsil_all = pd.concat(tehsil_frames, ignore_index=True)
    uc_all = pd.concat(uc_frames, ignore_index=True)

    for antigen in ["bcg", "penta1", "penta2", "penta3", "ipv1", "mr1", "ipv2", "tcv", "fic"]:
        district_all = _add_rag_columns(district_all, f"{antigen}_pct_reported")
        tehsil_all = _add_rag_columns(tehsil_all, f"{antigen}_pct_reported")
    district_all = _add_rag_columns(district_all, "dropout_pct_reported", "dropout_pct_reported")
    tehsil_all = _add_rag_columns(tehsil_all, "dropout_pct_reported", "dropout_pct_reported")

    for antigen in ["bcg", "penta1", "penta2", "penta3", "mr1", "fic", "tcv", "ipv1", "ipv2"]:
        uc_all["rag_" + antigen + "_pct"] = uc_all[antigen + "_pct"].apply(indicators.coverage_rag)
    uc_all["rag_dropout_pct"] = uc_all["dropout_pct"].apply(indicators.dropout_rag)

    print(f"\nWriting processed output to {processed_dir} ...")
    district_all.to_parquet(processed_dir / "coverage_district.parquet", index=False)
    tehsil_all.to_parquet(processed_dir / "coverage_tehsil.parquet", index=False)
    uc_all.to_parquet(processed_dir / "coverage_uc.parquet", index=False)
    print(f"  coverage_district.parquet: {len(district_all)} rows")
    print(f"  coverage_tehsil.parquet:   {len(tehsil_all)} rows")
    print(f"  coverage_uc.parquet:       {len(uc_all)} rows")

    flags_df = pd.DataFrame(log.flags)
    exclusions_df = pd.DataFrame(log.exclusions)
    if not flags_df.empty:
        flags_df.to_csv(processed_dir / "quality_flags.csv", index=False)
    if not exclusions_df.empty:
        exclusions_df.to_csv(processed_dir / "exclusions_log.csv", index=False)

    report = {
        "periods": [{"period_id": wb["period"].period_id, "label": wb["period"].label,
                     "source_file": wb["path"].name} for wb in workbooks],
        "row_counts": {"district": len(district_all), "tehsil": len(tehsil_all), "uc": len(uc_all)},
        "exclusions_total": len(log.exclusions),
        "flags_total": len(log.flags),
        "flags_by_type": flags_df["flag_type"].value_counts().to_dict() if not flags_df.empty else {},
        "exclusions_by_reason": (
            exclusions_df["reason"].value_counts().to_dict() if not exclusions_df.empty else {}
        ),
    }
    with open(processed_dir / "data_quality_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\nData quality summary:")
    print(f"  {len(log.exclusions)} rows excluded (see exclusions_log.csv)")
    print(f"  {len(log.flags)} rows flagged, kept in data (see quality_flags.csv)")
    for flag_type, count in report["flags_by_type"].items():
        print(f"    - {flag_type}: {count}")

    print("\nPipeline finished OK.")
    return report


if __name__ == "__main__":
    try:
        run()
    except SystemExit as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("\nUNEXPECTED FAILURE:", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
