"""Every indicator formula this system computes, one function each.

This is the single source of truth for indicator math. The dashboard and the
bulletin generator both read pipeline OUTPUT (data/processed/*), never call
these directly at render time, and never recompute an indicator themselves --
that's what keeps them mathematically incapable of disagreeing.

What's covered here vs. passed through, and why (see CLAUDE.md "Confirmed
decisions" for the full reasoning):

- District/Tehsil level coverage %, dropout %: COMPUTED here, from raw counts
  and targets that exist in the source file, and cross-checked against the
  sheet's own reported % in clean.py.
- UC level coverage %, dropout %, Access, Utilisation, Category: NOT computed
  here. The source file has no raw counts or targets at UC level, so there is
  nothing to compute from -- these are trusted as reported by clean.py.
- Access/Utilisation/Category at ANY level: NOT computed here at all, even
  though District/Tehsil have raw counts. The exact WHO-grid cutoff formula
  (which antigen, which % threshold) used to derive these labels in the
  source file has not been confirmed, so this pipeline does not guess it --
  see the "Open questions" section of CLAUDE.md. RAG (red/amber/green) rating
  bands below are a *separate*, confirmed-configurable display concept
  (config.COVERAGE_GOOD/WARNING) and are not the same thing as Category-1..4.
"""
from .config import COVERAGE_GOOD, COVERAGE_WARNING, DROPOUT_GOOD, DROPOUT_WARNING


def coverage_pct(count, target) -> float | None:
    """Antigen coverage % = (number vaccinated / target population) x 100.

    `target` is Target-for-BCG for the BCG antigen (birth cohort) and
    Target-for-surviving-infants for every other antigen in this dataset
    (Penta1-3, IPV1-2, MR1, TCV, FIC) -- confirmed by reproducing the
    reported % for Abbottabad, Dec 2025 to the sheet's own rounding
    (BCG: 2936/3527=83.2%->83 reported; Penta1: 3030/3339=90.8%->91 reported).
    Returns None when target is 0 or missing, rather than raising or
    returning 0 or inf -- a 0 target is a data problem (see
    'zero_target_div0' flags), not a legitimate 0% coverage result.
    """
    if target is None or target == 0:
        return None
    return count / target * 100


def penta_dropout_pct(penta1_count, penta3_count) -> float | None:
    """Penta1->Penta3 dropout % = (Penta1# - Penta3#) / Penta1# x 100.

    Standard EPI dropout formula. Confirmed against Abbottabad, Dec 2025:
    (3030-2853)/3030*100 = 5.84% -> 6 reported. A negative result means
    Penta3 > Penta1 at that district/tehsil/UC -- a data entry error, not a
    real negative dropout (more children can't complete dose 3 than started
    dose 1) -- flagged as 'negative_dropout', value kept as computed.
    Returns None when penta1_count is 0, to avoid a divide-by-zero.
    """
    if penta1_count is None or penta1_count == 0:
        return None
    return (penta1_count - penta3_count) / penta1_count * 100


def coverage_rag(pct) -> str | None:
    """Red/Amber/Green display band for a coverage %.

    >= COVERAGE_GOOD -> 'good'; >= COVERAGE_WARNING -> 'warning'; else 'poor'.
    Thresholds live in config.py, not hardcoded in any template. This is a
    display convenience, distinct from the source file's own Category-1..4
    grid (see module docstring) -- do not conflate the two in dashboard code.
    """
    if pct is None:
        return None
    if pct >= COVERAGE_GOOD:
        return "good"
    if pct >= COVERAGE_WARNING:
        return "warning"
    return "poor"


def dropout_rag(pct) -> str | None:
    """Red/Amber/Green display band for a dropout %.

    <= DROPOUT_GOOD -> 'good'; <= DROPOUT_WARNING -> 'warning'; else 'poor'.
    A negative dropout (data error, see penta_dropout_pct) still rates as
    'good' here since it is <= DROPOUT_GOOD -- the RAG band is not the place
    that surfaces the data-quality problem; the 'negative_dropout' flag is.
    """
    if pct is None:
        return None
    if pct <= DROPOUT_GOOD:
        return "good"
    if pct <= DROPOUT_WARNING:
        return "warning"
    return "poor"
