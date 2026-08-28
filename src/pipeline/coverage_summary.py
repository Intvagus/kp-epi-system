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

from .config import COVERAGE_GOOD, COVERAGE_WARNING, DISTRICT_TO_BOUNDARY, OUTLIER_PCT_THRESHOLD
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

# DISTRICT_TO_BOUNDARY (district name -> kp_districts.geojson boundary
# polygon name) now lives in config.py, shared with the Monitoring domain's
# district maps.


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


def _best_worst_district(district_rows: pd.DataFrame) -> dict:
    col = f"{SUMMARY_ANTIGEN}_pct_reported"
    # A district above the outlier threshold can't legitimately be called
    # "best" -- excluded from the best pick only; "worst" has no such
    # problem since low values are
    # never outliers.
    valid = district_rows[district_rows[col].notna() & (district_rows[col] <= OUTLIER_PCT_THRESHOLD)]
    worst_valid = district_rows[district_rows[col].notna()]
    if valid.empty or worst_valid.empty:
        return {"best": None, "worst": None}
    best_row = valid.loc[valid[col].idxmax()]
    worst_row = worst_valid.loc[worst_valid[col].idxmin()]
    return {
        "best": {"district": best_row["district"], "pct": _r(best_row[col])},
        "worst": {"district": worst_row["district"], "pct": _r(worst_row[col])},
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
    districts_current = _district_rows(district_all, period_id)

    antigen_extremes = _best_worst_antigen(prov)
    district_extremes = _best_worst_district(districts_current)
    district_compliance = _compliance_counts(districts_current[f"{SUMMARY_ANTIGEN}_pct_reported"])

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
    if district_compliance["total_with_data"]:
        insight_parts.append(
            f"{district_compliance['good']} of the {district_compliance['total_with_data']} districts "
            f"({district_compliance['compliant_pct']:.1f}%) have reached the {COVERAGE_GOOD}% FIC target; "
            f"{district_compliance['warning'] + district_compliance['poor']} district(s) require intervention."
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
        "best_district": district_extremes["best"], "worst_district": district_extremes["worst"],
        "district_compliance": district_compliance,
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
    # A UC above the outlier threshold is a known data-entry artifact
    # (see clean.py's is_outlier flag), not a real
    # top performer -- excluded from "top" only, since low values are never
    # outliers and "bottom" has no equivalent problem.
    top_ranked = valid[valid[col] <= OUTLIER_PCT_THRESHOLD].sort_values(col, ascending=False)
    bottom_ranked = valid.sort_values(col, ascending=False)
    top = top_ranked.head(5)[["uc_name", "district", col]].rename(columns={col: "pct"})
    bottom = bottom_ranked.tail(5)[["uc_name", "district", col]].rename(columns={col: "pct"}).iloc[::-1]

    fic = by_antigen.get("FIC", {})
    insight_parts = []
    if fic.get("total_with_data"):
        insight_parts.append(
            f"{fic['good']} of {fic['total_with_data']} Union Councils ({fic['compliant_pct']:.1f}%) have "
            f"reached the {COVERAGE_GOOD}% FIC (Fully Immunized Child) target; "
            f"{fic['poor']} UC(s) are in the critical band and need priority intervention."
        )
    if not top.empty and not bottom.empty:
        best_row, worst_row = top.iloc[0], bottom.iloc[0]
        insight_parts.append(
            f"{best_row['uc_name']} ({best_row['district']}) has the highest FIC coverage at "
            f"{best_row['pct']:.1f}%; {worst_row['uc_name']} ({worst_row['district']}) has the lowest "
            f"at {worst_row['pct']:.1f}%."
        )
    insight = " ".join(insight_parts) or "Not enough Union Council-level data this period to generate an insight."

    return {
        "period_id": period_id,
        "summary_antigen": "FIC",
        "by_antigen": by_antigen,
        "top_ucs": top.to_dict(orient="records"),
        "bottom_ucs": bottom.to_dict(orient="records"),
        "insight": insight,
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
            "vaccinated": None if pd.isna(prov[n_col]) else int(prov[n_col]),
            "target": None if pd.isna(prov[target_col]) else int(prov[target_col]),
            "pct": _r(pct),
            "rag": coverage_rag(pct),
        })
    rows.sort(key=lambda r: (r["pct"] is None, r["pct"] if r["pct"] is not None else 0), reverse=True)
    return rows


def _antigen_insight(rows: list[dict]) -> str:
    valid = [r for r in rows if r["pct"] is not None]
    if not valid:
        return "Not enough antigen-level data this period to generate an insight."
    best, worst = valid[0], valid[-1]
    parts = [
        f"{best['antigen']} has the highest coverage at {best['pct']:.1f}% "
        f"({best['vaccinated']:,} of {best['target']:,} children vaccinated), while {worst['antigen']} "
        f"has the lowest at {worst['pct']:.1f}%."
    ]
    # Matches the chart's own two-color logic (green/red split at
    # COVERAGE_GOOD) rather than the three-band RAG used elsewhere, so the
    # insight text never contradicts what the chart is showing.
    below_target = [r["antigen"] for r in valid if r["pct"] < COVERAGE_GOOD]
    if below_target:
        verb = "is" if len(below_target) == 1 else "are"
        parts.append(f"{', '.join(below_target)} {verb} below the {COVERAGE_GOOD}% target and need attention.")
    return " ".join(parts)


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
        ranked = valid.sort_values("gap", ascending=False).head(5)
        by_antigen[label] = [
            {
                "district": r["district"], "target": int(r[target_col]), "vaccinated": int(r[n_col]),
                "gap": int(r["gap"]), "pct_achievement": _r(r["pct_achievement"]),
            }
            for _, r in ranked.iterrows()
        ]

    insight_by_antigen = {}
    for label, rows in by_antigen.items():
        if rows:
            top = rows[0]
            insight_by_antigen[label] = (
                f"{top['district']} has the largest {label} immunization gap: {top['gap']:,} children "
                f"still unvaccinated against a target of {top['target']:,} ({top['pct_achievement']:.1f}% achieved)."
            )
        else:
            insight_by_antigen[label] = f"No district-level target data available for {label} this period."

    return {"period_id": period_id, "by_antigen": by_antigen, "insight_by_antigen": insight_by_antigen}


def build_dropout_analysis(district_all: pd.DataFrame, uc_all: pd.DataFrame, period_id: str) -> dict:
    """District-level Penta1->Penta3 dropout, ranked highest and lowest.

    This is the Excel's own explicit dropout figure, not a derived one -- the
    District sheet has its own "Drop Out" column (indicators.penta_dropout_pct
    cross-checks it against Penta1#/Penta3# but the value shown here, like
    everywhere else in this pipeline, is what the sheet itself reports).
    """
    districts = _district_rows(district_all, period_id)
    uc_period = uc_all[uc_all["period_id"] == period_id]

    valid = districts[districts["dropout_pct_reported"].notna()]
    highest = valid.sort_values("dropout_pct_reported", ascending=False).head(5)
    # A negative dropout is a data-entry artifact (Penta3# > Penta1#, flagged
    # as is_negative_dropout elsewhere), not a genuine best performer --
    # excluded from "lowest" only, same principle already used to keep
    # outlier values out of every other "best" pick in this module.
    lowest_valid = valid[~valid["is_negative_dropout"]]
    lowest = lowest_valid.sort_values("dropout_pct_reported", ascending=True).head(5)

    insight_parts = []
    if not highest.empty:
        top_d = highest.iloc[0]
        insight_parts.append(
            f"{top_d['district']} has the highest Penta1-to-Penta3 dropout at "
            f"{top_d['dropout_pct_reported']:.1f}%, meaning many children who started the Penta series "
            f"did not complete it."
        )
    if not lowest.empty:
        best_d = lowest.iloc[0]
        insight_parts.append(
            f"{best_d['district']} has the lowest dropout at {best_d['dropout_pct_reported']:.1f}%."
        )
    neg_d = int(districts["is_negative_dropout"].sum())
    neg_u = int(uc_period["is_negative_dropout"].fillna(False).sum())
    if neg_d or neg_u:
        insight_parts.append(
            f"{neg_d} district(s) and {neg_u} UC(s) show a negative dropout rate, a data-entry error "
            f"(more children recorded for Penta3 than Penta1), kept and flagged rather than removed."
        )

    return {
        "period_id": period_id,
        "negative_dropout_districts": neg_d,
        "negative_dropout_ucs": neg_u,
        "highest_districts": [
            {"district": r["district"], "dropout_pct": _r(r["dropout_pct_reported"])}
            for _, r in highest.iterrows()
        ],
        "lowest_districts": [
            {"district": r["district"], "dropout_pct": _r(r["dropout_pct_reported"])}
            for _, r in lowest.iterrows()
        ],
        "insight": " ".join(insight_parts) or "Not enough dropout data this period to generate an insight.",
    }


def build_trends(district_all: pd.DataFrame, period_type: str) -> dict:
    """Trend between the two most recent periods of the SAME period_type --
    monthly-vs-monthly or cumulative-vs-cumulative only, never monthly vs
    cumulative (see build_executive_summary's docstring)."""
    kind_label = "monthly" if period_type == "monthly" else "cumulative"
    trend_label = "month-over-month" if period_type == "monthly" else "year-over-year"
    periods = sorted(district_all.loc[district_all["period_type"] == period_type, "period_id"].unique())
    if len(periods) < 2:
        file_word = "file has" if len(periods) == 1 else "files have"
        return {
            "status": "insufficient_history",
            "periods_available": len(periods),
            "message": (
                f"Only {len(periods)} {kind_label} coverage {file_word} been uploaded so far. "
                f"A {trend_label} trend needs at least two {kind_label} periods -- this section "
                f"activates automatically once a second {kind_label} file is added, no rebuild needed."
            ),
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

    deltas = [(label, v["delta"]) for label, v in by_antigen.items() if v["delta"] is not None]
    if deltas:
        best_label, best_delta = max(deltas, key=lambda x: x[1])
        worst_label, worst_delta = min(deltas, key=lambda x: x[1])
        direction = "improved" if worst_delta >= 0 else "declined"
        insight = (
            f"From {prior_label} to {latest_label}, {best_label} improved the most "
            f"({best_delta:+.1f} percentage points), while {worst_label} {direction} the most "
            f"({worst_delta:+.1f} percentage points)."
        )
    else:
        insight = "Not enough matching antigen data between these two periods to generate an insight."

    return {
        "status": "ok", "latest_label": latest_label, "prior_label": prior_label,
        "by_antigen": by_antigen, "insight": insight,
    }


def build_district_map(district_all: pd.DataFrame, period_id: str) -> dict:
    """Per-boundary-polygon coverage figures for the district choropleth map.

    Some of our districts are newer sub-splits of the boundary set's older,
    coarser districts (see DISTRICT_TO_BOUNDARY) -- those are combined onto
    one polygon by summing raw counts/targets, never by averaging percentages,
    same rule as every other aggregate in this pipeline."""
    districts = _district_rows(district_all, period_id)
    unmapped = sorted(set(districts["district"]) - set(DISTRICT_TO_BOUNDARY))

    by_boundary = {}
    for boundary_name in sorted(set(DISTRICT_TO_BOUNDARY.values())):
        component_districts = sorted(d for d, b in DISTRICT_TO_BOUNDARY.items() if b == boundary_name)
        rows = districts[districts["district"].isin(component_districts)]
        by_antigen = {}
        for key, label in DISTRICT_ANTIGENS:
            n_col, target_col = (
                (f"{key}_n", "target_bcg") if key == "bcg" else (f"{key}_n", "target_surviving_infants")
            )
            vaccinated = rows[n_col].sum() if not rows.empty else None
            target = rows[target_col].sum() if not rows.empty else None
            pct = (vaccinated / target * 100) if target else None
            by_antigen[label] = {
                "vaccinated": None if vaccinated is None else int(vaccinated),
                "target": None if target is None else int(target),
                "pct": _r(pct),
                "rag": coverage_rag(pct),
            }
        by_boundary[boundary_name] = {
            "component_districts": component_districts,
            "by_antigen": by_antigen,
        }

    return {
        "period_id": period_id,
        # Should always be empty -- flagged loudly here rather than silently
        # dropped if a future district name doesn't have a boundary mapping.
        "unmapped_districts": unmapped,
        "features": by_boundary,
    }


def build_period_summary(district_all: pd.DataFrame, uc_all: pd.DataFrame, period_id: str, period_type: str) -> dict:
    """All 6 dashboard sections for ONE period, standalone."""
    executive = build_executive_summary(district_all, uc_all, period_id)
    if executive["status"] != "ok":
        return {"status": "no_data"}
    antigen_rows = build_antigen_analysis(district_all, period_id)
    return {
        "status": "ok",
        "executive": executive,
        "uc_compliance": build_uc_compliance(uc_all, period_id),
        "antigen_analysis": antigen_rows,
        "antigen_insight": _antigen_insight(antigen_rows),
        "target_gap": build_target_gap(district_all, period_id),
        "dropout": build_dropout_analysis(district_all, uc_all, period_id),
        "trends": build_trends(district_all, period_type),
        "district_map": build_district_map(district_all, period_id),
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
