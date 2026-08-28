"""Clean raw sheets into tidy per-level tables. Every exclusion is logged, never silent.

District/Tehsil levels have raw counts + targets, so this module independently
computes coverage % and dropout % and cross-checks them against the sheet's own
reported values (mismatches are flagged, not silently trusted or silently fixed).
UC level has no raw counts anywhere in the source file, so UC-level %, dropout,
Access, Utilisation and Category are trusted as reported and passed through
unchanged -- see CLAUDE.md "Confirmed decisions".
"""
from dataclasses import dataclass, field

import pandas as pd

from . import indicators
from .config import (
    JUNK_TEHSIL_DISTRICT_MARKERS,
    OUTLIER_PCT_THRESHOLD,
    PROVINCE_TOTAL_DISTRICT_LABEL,
    PROVINCE_TOTAL_NAME,
)

ANTIGENS_WITH_TARGET_SURVIVING_INFANTS = [
    "penta1", "penta2", "penta3", "ipv1", "mr1", "ipv2", "tcv", "fic",
]

DISTRICT_RENAME = {
    "S No": "s_no", "District": "district",
    "Target for BCG": "target_bcg", "Target for surviving infants": "target_surviving_infants",
    "BCG, #": "bcg_n", "BCG, %": "bcg_pct_reported",
    "P I #": "penta1_n", "P I %": "penta1_pct_reported",
    "P II #": "penta2_n", "P II %": "penta2_pct_reported",
    "PIII #": "penta3_n", "PIII %": "penta3_pct_reported",
    "IPV I #": "ipv1_n", "IPV I %": "ipv1_pct_reported",
    "MR I #": "mr1_n", "MR I %": "mr1_pct_reported",
    "IPV II #": "ipv2_n", "IPV II %": "ipv2_pct_reported",
    "TCV #": "tcv_n", "TCV %": "tcv_pct_reported",
    "FIC #": "fic_n", "FIC %": "fic_pct_reported",
    "Drop Out": "dropout_pct_reported",
    "District - Access": "access_rating", "District - Utilization": "utilisation_rating",
    "District Category": "category",
    "Category - 1": "cat1_count", "Category - 2": "cat2_count",
    "Category - 3": "cat3_count", "Category - 4": "cat4_count",
    "Total UCs": "total_ucs",
}

# Tehsil sheet's first 32 columns match District's shape (+ Tehsil name/code).
# Positional rename because the sheet's second, unrelated column block re-uses
# header names ('District', 'Category - 1'...) which pandas would otherwise
# collide with and silently suffix (.1, .2) -- see CLAUDE.md re: the 'Check' block.
TEHSIL_COLUMNS_ORDERED = [
    "district", "tehsil", "tehsil_code", "target_bcg", "target_surviving_infants",
    "bcg_n", "bcg_pct_reported", "penta1_n", "penta1_pct_reported",
    "penta2_n", "penta2_pct_reported", "penta3_n", "penta3_pct_reported",
    "ipv1_n", "ipv1_pct_reported", "mr1_n", "mr1_pct_reported",
    "ipv2_n", "ipv2_pct_reported", "tcv_n", "tcv_pct_reported",
    "fic_n", "fic_pct_reported", "dropout_pct_reported",
    "access_rating", "utilisation_rating", "category",
    "cat1_count", "cat2_count", "cat3_count", "cat4_count", "total_ucs",
]

UC_COVERAGES_RENAME = {
    "District": "district", "Tehsil": "tehsil", "Tehsil Code": "tehsil_code",
    "Union Council Code": "uc_code", "UnionCouncil": "uc_name",
    "BCG %": "bcg_pct", "OPV 0%": "opv0_pct", "OPV I%": "opv1_pct",
    "OPV II %": "opv2_pct", "OPV III %": "opv3_pct",
    "Penta I %": "penta1_pct", "Penta II %": "penta2_pct", "Penta III %": "penta3_pct",
    "PCV I 10 %": "pcv1_pct", "PCV II 10 %": "pcv2_pct", "PCV III 10 %": "pcv3_pct",
    "IPV I %": "ipv1_pct", "Rota I %": "rota1_pct", "Rota II %": "rota2_pct",
    "MR I %": "mr1_pct", "FIC %": "fic_pct", "TCV %": "tcv_pct", "IPV II %": "ipv2_pct",
    "Dropout (P1 - P3), %": "dropout_pct", "Access": "access_rating",
    "Utilisation": "utilisation_rating", "Category": "category",
}
UC_PCT_COLUMNS = [
    "bcg_pct", "opv0_pct", "opv1_pct", "opv2_pct", "opv3_pct", "penta1_pct",
    "penta2_pct", "penta3_pct", "pcv1_pct", "pcv2_pct", "pcv3_pct", "ipv1_pct",
    "rota1_pct", "rota2_pct", "mr1_pct", "fic_pct", "tcv_pct", "ipv2_pct",
]

UC_DIFFERENCE_RENAME = {
    "Union Council Code": "uc_code",
    "BCG-OPV0": "diff_bcg_opv0", "P1-OPV1": "diff_p1_opv1", "P1-pcv1": "diff_p1_pcv1",
    "P1-R1": "diff_p1_r1", "P2-OPV2": "diff_p2_opv2", "P2-pcv2": "diff_p2_pcv2",
    "P2-R2": "diff_p2_r2", "P3-OPV3": "diff_p3_opv3", "P3-pcv3": "diff_p3_pcv3",
    "P3-IPV1": "diff_p3_ipv1", "MR1 - TCV": "diff_mr1_tcv",
}
DIFFERENCE_COLS = [
    "diff_bcg_opv0", "diff_p1_opv1", "diff_p1_pcv1", "diff_p1_r1", "diff_p2_opv2",
    "diff_p2_pcv2", "diff_p2_r2", "diff_p3_opv3", "diff_p3_pcv3", "diff_p3_ipv1",
    "diff_mr1_tcv",
]


@dataclass
class QualityLog:
    flags: list = field(default_factory=list)      # kept rows, flagged
    exclusions: list = field(default_factory=list)  # dropped rows, with reason

    def flag(self, period_id, level, entity, flag_type, detail=""):
        self.flags.append({
            "period_id": period_id, "level": level, "entity": entity,
            "flag_type": flag_type, "detail": detail,
        })

    def exclude(self, period_id, level, entity, reason):
        self.exclusions.append({
            "period_id": period_id, "level": level, "entity": entity, "reason": reason,
        })


def _crosscheck(df: pd.DataFrame, period_id: str, level: str, log: QualityLog, tol: float = 1.5):
    """Compute coverage %/dropout % from raw counts (via indicators.py -- the
    single source of truth for these formulas) and flag disagreement with the
    sheet's own reported %. Does not overwrite the reported value."""
    df["bcg_pct_computed"] = df.apply(
        lambda r: indicators.coverage_pct(r["bcg_n"], r["target_bcg"]), axis=1
    )
    for antigen in ANTIGENS_WITH_TARGET_SURVIVING_INFANTS:
        n_col, computed_col = f"{antigen}_n", f"{antigen}_pct_computed"
        df[computed_col] = df.apply(
            lambda r, n_col=n_col: indicators.coverage_pct(r[n_col], r["target_surviving_infants"]),
            axis=1,
        )

    df["dropout_pct_computed"] = df.apply(
        lambda r: indicators.penta_dropout_pct(r["penta1_n"], r["penta3_n"]), axis=1
    )

    entity_col = "district" if level == "district" else "tehsil"
    check_cols = ["bcg"] + ANTIGENS_WITH_TARGET_SURVIVING_INFANTS
    for antigen in check_cols:
        reported, computed = f"{antigen}_pct_reported", f"{antigen}_pct_computed"
        diff = (df[reported] - df[computed]).abs()
        mismatched = df[diff > tol]
        for _, row in mismatched.iterrows():
            log.flag(period_id, level, row[entity_col], "pct_mismatch", detail=(
                f"{antigen}: reported={row[reported]}, computed={round(row[computed], 1)}"
            ))

    diff = (df["dropout_pct_reported"] - df["dropout_pct_computed"]).abs()
    for _, row in df[diff > tol].iterrows():
        log.flag(period_id, level, row[entity_col], "dropout_mismatch", detail=(
            f"reported={row['dropout_pct_reported']}, computed={round(row['dropout_pct_computed'], 1)}"
        ))

    neg = df[df["dropout_pct_reported"] < 0]
    for _, row in neg.iterrows():
        log.flag(period_id, level, row[entity_col], "negative_dropout",
                  detail=str(row["dropout_pct_reported"]))
    df["is_negative_dropout"] = df["dropout_pct_reported"] < 0

    return df


def clean_district(raw_df: pd.DataFrame, period_id: str, log: QualityLog):
    df = raw_df.rename(columns=DISTRICT_RENAME).copy()
    # access_rating/utilisation_rating/category are text labels (Good/Poor/Category-N);
    # any Excel error string there just becomes null, no numeric coercion needed.
    for col in ["access_rating", "utilisation_rating", "category"]:
        is_err = df[col].astype(str).str.startswith("#", na=False)
        for entity in df.loc[is_err, "district"]:
            log.flag(period_id, "district", entity, "zero_target_div0", detail=col)
        df[col] = df[col].where(~is_err, None)

    df["is_province_total"] = df["district"] == PROVINCE_TOTAL_DISTRICT_LABEL
    if df["is_province_total"].any():
        log.flag(period_id, "district", PROVINCE_TOTAL_DISTRICT_LABEL, "province_total_mislabeled",
                  detail="Row labelled 'Tor Ghar' is actually the KP province total; real Tor Ghar "
                         "district data is missing from this file.")
    df.loc[df["is_province_total"], "district"] = PROVINCE_TOTAL_NAME

    df = _crosscheck(df, period_id, "district", log)
    df["period_id"] = period_id
    return df


def clean_tehsil(raw_df: pd.DataFrame, period_id: str, log: QualityLog):
    first_block = raw_df.iloc[:, :32].copy()
    first_block.columns = TEHSIL_COLUMNS_ORDERED

    is_junk = first_block["district"].isin(JUNK_TEHSIL_DISTRICT_MARKERS) | first_block["district"].isna()
    for _, row in first_block[is_junk].iterrows():
        log.exclude(period_id, "tehsil", row["tehsil"],
                    "district field is null/'\\N' and target is 0 -- junk export row")
    df = first_block[~is_junk].reset_index(drop=True)

    for col in ["access_rating", "utilisation_rating", "category"]:
        is_err = df[col].astype(str).str.startswith("#", na=False)
        for entity in df.loc[is_err, "tehsil"]:
            log.flag(period_id, "tehsil", entity, "zero_target_div0", detail=col)
        df[col] = df[col].where(~is_err, None)

    df = _crosscheck(df, period_id, "tehsil", log)
    df["period_id"] = period_id
    return df


def clean_uc(coverages_raw: pd.DataFrame, difference_raw: pd.DataFrame, period_id: str, log: QualityLog):
    df = coverages_raw.rename(columns=UC_COVERAGES_RENAME).copy()

    zero_target_mask = pd.Series(False, index=df.index)
    for col in UC_PCT_COLUMNS + ["dropout_pct"]:
        is_err = df[col].astype(str).str.startswith("#", na=False)
        zero_target_mask |= is_err
        for uc_name in df.loc[is_err, "uc_name"]:
            log.flag(period_id, "uc", uc_name, "zero_target_div0", detail=col)
        df[col] = pd.to_numeric(df[col], errors="coerce")
    # Access/Utilisation/Category hit #DIV/0! at UC level whenever the UC has a
    # zero target -- confirmed against the source file: the 56 UCs flagged here
    # for Dec 2025 have clean antigen %s but error strings in exactly these
    # three columns, since the Access/Utilisation formula divides by a
    # different (zero) denominator than the antigen coverage %s do.
    for col in ["access_rating", "utilisation_rating", "category"]:
        is_err = df[col].astype(str).str.startswith("#", na=False)
        zero_target_mask |= is_err
        for uc_name in df.loc[is_err, "uc_name"]:
            log.flag(period_id, "uc", uc_name, "zero_target_div0", detail=col)
        df[col] = df[col].where(~is_err, None)

    df["is_zero_target"] = zero_target_mask

    outlier_mask = pd.Series(False, index=df.index)
    for col in UC_PCT_COLUMNS:
        col_outlier = df[col] > OUTLIER_PCT_THRESHOLD
        outlier_mask |= col_outlier.fillna(False)
        for uc_name in df.loc[col_outlier.fillna(False), "uc_name"]:
            log.flag(period_id, "uc", uc_name, "outlier_pct_gt_threshold",
                      detail=f"{col}={df.loc[df['uc_name'] == uc_name, col].values[0]}")
    df["is_outlier"] = outlier_mask

    df["is_negative_dropout"] = df["dropout_pct"] < 0
    for uc_name in df.loc[df["is_negative_dropout"].fillna(False), "uc_name"]:
        log.flag(period_id, "uc", uc_name, "negative_dropout")

    diff = difference_raw.rename(columns=UC_DIFFERENCE_RENAME)[["uc_code"] + DIFFERENCE_COLS]
    diff = diff.dropna(subset=["uc_code"]).drop_duplicates(subset=["uc_code"])
    diff["is_consistency_fail"] = (diff[DIFFERENCE_COLS] != 0).any(axis=1)
    diff["consistency_fail_count"] = (diff[DIFFERENCE_COLS] != 0).sum(axis=1)

    df = df.merge(diff, on="uc_code", how="left")
    missing_diff = df["is_consistency_fail"].isna()
    if missing_diff.any():
        for uc_name in df.loc[missing_diff, "uc_name"]:
            log.flag(period_id, "uc", uc_name, "no_consistency_data",
                      detail="UC code not found in Difference sheet")
    df["is_consistency_fail"] = df["is_consistency_fail"].fillna(False)

    for _, row in df[df["is_consistency_fail"]].iterrows():
        _count = int(row["consistency_fail_count"])
        log.flag(period_id, "uc", row["uc_name"], "same_visit_consistency_fail",
                  detail=f"{_count} antigen {'pair disagrees' if _count == 1 else 'pairs disagree'}")

    df["period_id"] = period_id
    return df
