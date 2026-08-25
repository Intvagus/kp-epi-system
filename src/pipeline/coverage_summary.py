"""Derived, higher-level coverage analytics for the dashboard's Coverage tab
(executive KPIs, UC compliance banding, antigen comparison, target-vs-coverage
gaps, dropout ranking, month-over-month trend).

Same rule as everywhere else in this pipeline: this module is the only place
these numbers get computed. The dashboard reads the output JSON and never
recalculates anything -- see indicators.py's module docstring for why.

Only antigens that actually exist with raw counts + targets in the District/
Tehsil sheets are analysed here (BCG, Penta1-3, IPV1-2, MR1, TCV, FIC) --
OPV/PCV/Rota/MR2 and any sex (male/female) breakdown do not exist anywhere in
the source files, so nothing here fabricates them.
"""
import pandas as pd

from .config import COVERAGE_GOOD, COVERAGE_WARNING, OUTLIER_PCT_THRESHOLD
from .indicators import coverage_rag, dropout_rag

# District/Tehsil-level antigens that have both a raw count and a target in
# the source file, i.e. everything indicators.coverage_pct can legitimately
# be computed for. Order matches the sheet's own column order.
DISTRICT_ANTIGENS = [
    ("bcg", "BCG"), ("penta1", "Penta1"), ("penta2", "Penta2"), ("penta3", "Penta3"),
    ("ipv1", "IPV1"), ("ipv2", "IPV2"), ("mr1", "MR1"), ("tcv", "TCV"), ("fic", "FIC"),
]

# UC-level has percentages only (no raw counts/targets -- see clean.py), but
# covers a wider antigen set than District/Tehsil (adds OPV, PCV, Rota).
UC_ANTIGENS = [
    ("bcg_pct", "BCG"), ("opv0_pct", "OPV0"), ("opv1_pct", "OPV1"), ("opv2_pct", "OPV2"),
    ("opv3_pct", "OPV3"), ("penta1_pct", "Penta1"), ("penta2_pct", "Penta2"),
    ("penta3_pct", "Penta3"), ("pcv1_pct", "PCV1"), ("pcv2_pct", "PCV2"), ("pcv3_pct", "PCV3"),
    ("ipv1_pct", "IPV1"), ("ipv2_pct", "IPV2"), ("rota1_pct", "Rota1"), ("rota2_pct", "Rota2"),
    ("mr1_pct", "MR1"), ("fic_pct", "FIC"), ("tcv_pct", "TCV"),
]

# The single antigen used to rank/rate a UC or district when a summary needs
# one number -- Fully Immunized Child is the standard EPI summary indicator
# and is already what the existing Overview tab ranks districts by.
SUMMARY_ANTIGEN = "fic"


def _r(v, nd: int = 1):
    """Round to a plain Python float, or None for NaN. Several source columns
    (e.g. the sheet's whole-number _pct_reported fields) are numpy int64 --
    round() on those returns numpy.int64, which json.dump can't serialize and
    silently stringifies via default=str. Always route through this instead."""
    return None if pd.isna(v) else round(float(v), nd)


def _pick_period(district_all: pd.DataFrame, period_type: str) -> str | None:
    periods = sorted(district_all.loc[district_all["period_type"] == period_type, "period_id"].unique())
    return periods[-1] if periods else None


def _province_row(district_all: pd.DataFrame, period_id: str) -> pd.Series | None:
    rows = district_all[(district_all["period_id"] == period_id) & (district_all["is_province_total"])]
    return rows.iloc[0] if not rows.empty else None


def _district_rows(district_all: pd.DataFrame, period_id: str) -> pd.DataFrame:
    return district_all[(district_all["period_id"] == period_id) & (~district_all["is_province_total"])]


def _best_worst_antigen(province_row: pd.Series) -> dict:
    pcts = {label: province_row[f"{key}_pct_reported"] for key, label in DISTRICT_ANTIGENS
            if pd.notna(province_row.get(f"{key}_pct_reported"))}
    if not pcts:
        return {"best": None, "worst": None}
    best = max(pcts, key=pcts.get)
    worst = min(pcts, key=pcts.get)
    return {
        "best": {"antigen": best, "pct": _r(pcts[best])},
        "worst": {"antigen": worst, "pct": _r(pcts[worst])},
    }


def _best_worst_uc(uc_period: pd.DataFrame) -> dict:
    col = f"{SUMMARY_ANTIGEN}_pct"
    # A UC with no target (null %) or an implausible >threshold% value can't
    # legitimately be called "best" -- excluded from the best pick only;
    # "worst" has no such problem since low values are never outliers.
    valid = uc_period[uc_period[col].notna() & (uc_period[col] <= OUTLIER_PCT_THRESHOLD)]
    worst_valid = uc_period[uc_period[col].notna()]
    if valid.empty or worst_valid.empty:
        return {"best": None, "worst": None}
    best_row = valid.loc[valid[col].idxmax()]
    worst_row = worst_valid.loc[worst_valid[col].idxmin()]
    return {
        "best": {"uc_name": best_row["uc_name"], "district": best_row["district"], "pct": _r(best_row[col])},
        "worst": {"uc_name": worst_row["uc_name"], "district": worst_row["district"], "pct": _r(worst_row[col])},
    }


def _compliance_counts(values: pd.Series) -> dict:
    valid = values.dropna()
    good = int((valid >= COVERAGE_GOOD).sum())
    warning = int(((valid >= COVERAGE_WARNING) & (valid < COVERAGE_GOOD)).sum())
    poor = int((valid < COVERAGE_WARNING).sum())
    total = len(valid)
    return {
        "good": good, "warning": warning, "poor": poor, "total_with_data": total,
        "compliant_pct": _r(good / total * 100) if total else None,
    }


def build_executive_summary(district_all: pd.DataFrame, uc_all: pd.DataFrame, period_id: str) -> dict:
    """Executive summary for ONE period (monthly or cumulative) in isolation.

    Deliberately does not compare across period types -- monthly and
    cumulative data are never merged or averaged together anywhere in this
    module (see build_coverage_summary), only ever shown as two separate,
    complete views."""
    prov = _province_row(district_all, period_id)
    if prov is None:
        return {"status": "no_data"}
    current_label = district_all[district_all["period_id"] == period_id]["period_label"].iloc[0]
    uc_current = uc_all[uc_all["period_id"] == period_id]

    antigen_extremes = _best_worst_antigen(prov)
    uc_extremes = _best_worst_uc(uc_current)
    compliance = _compliance_counts(uc_current[f"{SUMMARY_ANTIGEN}_pct"])

    fic_pct = prov["fic_pct_reported"]
    insight_parts = []
    if pd.notna(fic_pct):
        band = "meets" if fic_pct >= COVERAGE_GOOD else ("is approaching" if fic_pct >= COVERAGE_WARNING else "is below")
        insight_parts.append(
            f"Province-wide FIC (Fully Immunized Child) coverage for {current_label} is "
            f"{fic_pct:.1f}%, which {band} the {COVERAGE_GOOD}% good-coverage threshold."
        )
    if antigen_extremes["best"] and antigen_extremes["worst"]:
        insight_parts.append(
            f"{antigen_extremes['best']['antigen']} has the strongest coverage "
            f"({antigen_extremes['best']['pct']:.1f}%); {antigen_extremes['worst']['antigen']} the weakest "
            f"({antigen_extremes['worst']['pct']:.1f}%)."
        )
    if compliance["total_with_data"]:
        insight_parts.append(
            f"{compliance['compliant_pct']:.1f}% of the {compliance['total_with_data']} UCs with a valid "
            f"FIC figure meet the {COVERAGE_GOOD}% compliance threshold; "
            f"{compliance['warning'] + compliance['poor']} UC(s) require attention."
        )

    return {
        "status": "ok",
        "current_period_id": period_id, "current_period_label": current_label,
        "target_surviving_infants": None if pd.isna(prov["target_surviving_infants"]) else int(prov["target_surviving_infants"]),
        "target_bcg": None if pd.isna(prov["target_bcg"]) else int(prov["target_bcg"]),
        "fic_pct": _r(fic_pct),
        "fic_rag": coverage_rag(fic_pct),
        "dropout_pct": _r(prov["dropout_pct_reported"]),
        "dropout_rag": dropout_rag(prov["dropout_pct_reported"]),
        "best_antigen": antigen_extremes["best"], "worst_antigen": antigen_extremes["worst"],
        "best_uc": uc_extremes["best"], "worst_uc": uc_extremes["worst"],
        "uc_compliance": compliance,
        "insight": " ".join(insight_parts) or "Not enough valid data this period to generate an insight.",
    }


def build_uc_compliance(uc_all: pd.DataFrame, period_id: str) -> dict:
    uc_period = uc_all[uc_all["period_id"] == period_id]
    by_antigen = {}
    for key, label in UC_ANTIGENS:
        if key in uc_period.columns:
            by_antigen[label] = _compliance_counts(uc_period[key])

    col = f"{SUMMARY_ANTIGEN}_pct"
    valid = uc_period[uc_period[col].notna()]
    # Same reasoning as _best_worst_uc: a UC above the outlier threshold is a
    # known data-entry artifact (see clean.py's is_outlier flag), not a real
    # top performer -- excluded from "top" only, since low values are never
    # outliers and "bottom" has no equivalent problem.
    top_ranked = valid[valid[col] <= OUTLIER_PCT_THRESHOLD].sort_values(col, ascending=False)
    bottom_ranked = valid.sort_values(col, ascending=False)
    top = top_ranked.head(15)[["uc_name", "district", col]].rename(columns={col: "pct"})
    bottom = bottom_ranked.tail(15)[["uc_name", "district", col]].rename(columns={col: "pct"}).iloc[::-1]

    return {
        "period_id": period_id,
        "summary_antigen": "FIC",
        "by_antigen": by_antigen,
        "top_ucs": top.to_dict(orient="records"),
        "bottom_ucs": bottom.to_dict(orient="records"),
    }


def build_antigen_analysis(district_all: pd.DataFrame, period_id: str) -> list[dict]:
    prov = _province_row(district_all, period_id)
    if prov is None:
        return []
    rows = []
    for key, label in DISTRICT_ANTIGENS:
        n_col, target_col = (
            (f"{key}_n", "target_bcg") if key == "bcg" else (f"{key}_n", "target_surviving_infants")
        )
        pct = prov[f"{key}_pct_reported"]
        rows.append({
            "antigen": label,
            "covered": None if pd.isna(prov[n_col]) else int(prov[n_col]),
            "target": None if pd.isna(prov[target_col]) else int(prov[target_col]),
            "pct": _r(pct),
            "rag": coverage_rag(pct),
        })
    rows.sort(key=lambda r: (r["pct"] is None, r["pct"] if r["pct"] is not None else 0), reverse=True)
    return rows


def build_target_gap(district_all: pd.DataFrame, period_id: str) -> dict:
    districts = _district_rows(district_all, period_id)
    by_antigen = {}
    for key, label in DISTRICT_ANTIGENS:
        n_col, target_col = (
            (f"{key}_n", "target_bcg") if key == "bcg" else (f"{key}_n", "target_surviving_infants")
        )
        valid = districts[districts[target_col].notna() & (districts[target_col] > 0)].copy()
        valid["gap"] = valid[target_col] - valid[n_col]
        valid["pct_achievement"] = valid[n_col] / valid[target_col] * 100
        ranked = valid.sort_values("gap", ascending=False).head(10)
        by_antigen[label] = [
            {
                "district": r["district"], "target": int(r[target_col]), "covered": int(r[n_col]),
                "gap": int(r["gap"]), "pct_achievement": _r(r["pct_achievement"]),
            }
            for _, r in ranked.iterrows()
        ]
    return {"period_id": period_id, "by_antigen": by_antigen}


def build_dropout_analysis(district_all: pd.DataFrame, uc_all: pd.DataFrame, period_id: str) -> dict:
    districts = _district_rows(district_all, period_id)
    uc_period = uc_all[uc_all["period_id"] == period_id]

    district_ranked = districts[districts["dropout_pct_reported"].notna()].sort_values(
        "dropout_pct_reported", ascending=False
    ).head(10)
    uc_ranked = uc_period[uc_period["dropout_pct"].notna()].sort_values(
        "dropout_pct", ascending=False
    ).head(15)

    return {
        "period_id": period_id,
        "formula": "Penta1 -> Penta3 dropout = (Penta1# - Penta3#) / Penta1# x 100. "
                   "No other antigen pair in this dataset shares a common target denominator "
                   "with its earlier dose, so no other dropout indicator is computed.",
        "negative_dropout_districts": int(districts["is_negative_dropout"].sum()),
        "negative_dropout_ucs": int(uc_period["is_negative_dropout"].fillna(False).sum()),
        "worst_districts": [
            {"district": r["district"], "dropout_pct": _r(r["dropout_pct_reported"])}
            for _, r in district_ranked.iterrows()
        ],
        "worst_ucs": [
            {"uc_name": r["uc_name"], "district": r["district"], "dropout_pct": _r(r["dropout_pct"])}
            for _, r in uc_ranked.iterrows()
        ],
    }


def build_trends(district_all: pd.DataFrame, period_type: str) -> dict:
    """Trend between the two most recent periods of the SAME period_type --
    monthly-vs-monthly or cumulative-vs-cumulative only, never monthly vs
    cumulative (see build_executive_summary's docstring)."""
    kind_label = "monthly" if period_type == "monthly" else "cumulative"
    periods = sorted(district_all.loc[district_all["period_type"] == period_type, "period_id"].unique())
    if len(periods) < 2:
        return {
            "status": "insufficient_history",
            "periods_available": len(periods),
            "message": (
                "Only {} {} coverage file(s) have been uploaded so far. A {}-over-{} trend "
                "needs at least two {} periods -- this section activates automatically once a "
                "second {} file is added, no rebuild needed."
            ).format(len(periods), kind_label, kind_label, kind_label, kind_label, kind_label),
        }

    latest_id, prior_id = periods[-1], periods[-2]
    prov_latest = _province_row(district_all, latest_id)
    prov_prior = _province_row(district_all, prior_id)
    latest_label = district_all[district_all["period_id"] == latest_id]["period_label"].iloc[0]
    prior_label = district_all[district_all["period_id"] == prior_id]["period_label"].iloc[0]

    by_antigen = {}
    for key, label in DISTRICT_ANTIGENS:
        latest_pct, prior_pct = prov_latest[f"{key}_pct_reported"], prov_prior[f"{key}_pct_reported"]
        delta = (latest_pct - prior_pct) if pd.notna(latest_pct) and pd.notna(prior_pct) else None
        by_antigen[label] = {
            "latest_pct": _r(latest_pct),
            "prior_pct": _r(prior_pct),
            "delta": _r(delta) if delta is not None else None,
        }

    return {
        "status": "ok", "latest_label": latest_label, "prior_label": prior_label,
        "by_antigen": by_antigen,
    }


def build_period_summary(district_all: pd.DataFrame, uc_all: pd.DataFrame, period_id: str, period_type: str) -> dict:
    """All 6 dashboard sections for ONE period, standalone."""
    executive = build_executive_summary(district_all, uc_all, period_id)
    if executive["status"] != "ok":
        return {"status": "no_data"}
    return {
        "status": "ok",
        "executive": executive,
        "uc_compliance": build_uc_compliance(uc_all, period_id),
        "antigen_analysis": build_antigen_analysis(district_all, period_id),
        "target_gap": build_target_gap(district_all, period_id),
        "dropout": build_dropout_analysis(district_all, uc_all, period_id),
        "trends": build_trends(district_all, period_type),
    }


def build_coverage_summary(district_all: pd.DataFrame, uc_all: pd.DataFrame) -> dict:
    """Two fully independent period views -- monthly and cumulative are never
    merged or compared against each other, only ever shown side by side as
    separate complete dashboards (each with all 6 sections)."""
    monthly_id = _pick_period(district_all, "monthly")
    cumulative_id = _pick_period(district_all, "cumulative_annual")

    periods = {
        "monthly": (build_period_summary(district_all, uc_all, monthly_id, "monthly")
                    if monthly_id else {"status": "no_data"}),
        "cumulative": (build_period_summary(district_all, uc_all, cumulative_id, "cumulative_annual")
                       if cumulative_id else {"status": "no_data"}),
    }
    if periods["monthly"]["status"] != "ok" and periods["cumulative"]["status"] != "ok":
        return {"status": "no_data"}
    return {"status": "ok", "periods": periods}
