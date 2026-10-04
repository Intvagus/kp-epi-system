"""Regression test for a real bug found 2026-10: build_executive_summary()
(and everything downstream of it -- build_antigen_analysis, build_trends)
silently returned {"status": "no_data"} whenever the District sheet had no
explicit province-total row (the source system's own convention is a row
literally labelled "Tor Ghar" -- see CLAUDE.md). Every real sample file
received so far happens to have this row, but it's a genuinely non-obvious
requirement for anyone hand-building a Coverage file from the template --
confirmed by the fact that the first version of this project's own Coverage
template omitted it, silently producing a "no data" Executive Overview and
Service Delivery tab despite perfectly valid per-district numbers being
present everywhere else.

Fixed with a fallback (_computed_province_row in coverage_summary.py): when
no is_province_total row exists, a province total is computed by summing
real counts/targets across the real district rows and recomputing
percentages from those sums -- never averaging reported percentages, same
"sum counts, don't average %" rule as every other province-wide aggregate
in that module. Uses small synthetic DataFrames (not real sample files, all
of which already have a province-total row) so this exact scenario is
always exercised regardless of which real files are present.
"""
import pandas as pd
import pytest

from src.pipeline.coverage_summary import build_antigen_analysis, build_coverage_summary, build_executive_summary
from src.pipeline.indicators import coverage_pct, penta_dropout_pct


def _antigen_cols():
    cols = {}
    for key in ["bcg", "penta1", "penta2", "penta3", "ipv1", "ipv2", "mr1", "tcv", "fic"]:
        cols[f"{key}_n"] = 0
        cols[f"{key}_pct_reported"] = 0
    return cols


def _district_row(district, is_province_total, bcg_n, penta1_n, penta3_n, target_bcg, target_surviving):
    row = {
        "district": district, "is_province_total": is_province_total,
        "period_id": "2026-03", "period_type": "monthly", "period_label": "Mar 2026",
        "target_bcg": target_bcg, "target_surviving_infants": target_surviving,
        "cat1_count": 1, "cat2_count": 0, "cat3_count": 0, "cat4_count": 0, "total_ucs": 5,
        **_antigen_cols(),
    }
    row["bcg_n"] = bcg_n
    row["bcg_pct_reported"] = coverage_pct(bcg_n, target_bcg)
    row["penta1_n"] = penta1_n
    row["penta1_pct_reported"] = coverage_pct(penta1_n, target_surviving)
    row["penta3_n"] = penta3_n
    row["penta3_pct_reported"] = coverage_pct(penta3_n, target_surviving)
    dropout = penta_dropout_pct(penta1_n, penta3_n)
    row["dropout_pct_reported"] = dropout
    row["is_negative_dropout"] = dropout is not None and dropout < 0
    for key in ["penta2", "ipv1", "ipv2", "mr1", "tcv", "fic"]:
        row[f"{key}_n"] = penta1_n
        row[f"{key}_pct_reported"] = coverage_pct(penta1_n, target_surviving)
    return row


@pytest.fixture
def district_all_no_province_row():
    rows = [
        _district_row("Abbottabad", False, bcg_n=800, penta1_n=750, penta3_n=700, target_bcg=1000, target_surviving=950),
        _district_row("Bannu", False, bcg_n=600, penta1_n=500, penta3_n=400, target_bcg=800, target_surviving=750),
    ]
    return pd.DataFrame(rows)


@pytest.fixture
def uc_all_empty():
    return pd.DataFrame(columns=[
        "district", "period_id", "fic_pct", "uc_name", "tehsil",
        "is_negative_dropout", "dropout_pct", "is_zero_target", "is_outlier",
    ])


def test_executive_summary_ok_without_a_province_total_row(district_all_no_province_row, uc_all_empty):
    result = build_executive_summary(district_all_no_province_row, uc_all_empty, "2026-03")
    assert result["status"] == "ok"
    # Summed real counts/targets, not an average of reported %s:
    # BCG: (800+600)/(1000+800) * 100 = 77.8%
    assert result is not None
    assert "fic_pct" in result


def test_antigen_analysis_not_empty_without_a_province_total_row(district_all_no_province_row):
    rows = build_antigen_analysis(district_all_no_province_row, "2026-03")
    assert rows  # was [] before the fix
    bcg = next(r for r in rows if r["antigen"] == "BCG")
    assert bcg["vaccinated"] == 800 + 600
    assert bcg["target"] == 1000 + 800
    assert bcg["pct"] == pytest.approx(round(1400 / 1800 * 100, 1), abs=0.1)


def test_build_coverage_summary_status_ok_without_a_province_total_row(district_all_no_province_row, uc_all_empty):
    summary = build_coverage_summary(district_all_no_province_row, uc_all_empty)
    assert summary["status"] == "ok"
    assert summary["periods"]["monthly"]["status"] == "ok"


def test_real_province_total_row_still_takes_priority_when_present(district_all_no_province_row, uc_all_empty):
    """A real is_province_total row must still be trusted as-is and NOT
    overridden by the computed fallback -- zero behavior change for every
    real file that already has one."""
    province_row = _district_row(
        "Tor Ghar", True, bcg_n=999999, penta1_n=999999, penta3_n=999999,
        target_bcg=999999, target_surviving=999999,
    )
    province_row["fic_pct_reported"] = 12.3  # a value the computed fallback could never produce
    district_all = pd.concat([district_all_no_province_row, pd.DataFrame([province_row])], ignore_index=True)
    result = build_executive_summary(district_all, uc_all_empty, "2026-03")
    assert result["status"] == "ok"
    assert result["fic_pct"] == 12.3
