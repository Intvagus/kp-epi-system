"""Every indicator formula tested against known values, mostly taken directly
from Abbottabad, December 2025 (data/raw/Dec 2025 Coverage Analysis (0-11).xlsx,
District sheet, row 1) so the tests are pinned to real numbers, not invented ones.
"""
import pytest

from src.pipeline.config import COVERAGE_GOOD, COVERAGE_WARNING, DROPOUT_GOOD, DROPOUT_WARNING
from src.pipeline.indicators import coverage_pct, coverage_rag, dropout_rag, penta_dropout_pct


def test_coverage_pct_bcg_matches_reported_abbottabad_dec2025():
    # BCG#=2936, Target for BCG=3527, sheet reports 83%
    pct = coverage_pct(2936, 3527)
    assert round(pct) == 83


def test_coverage_pct_penta1_matches_reported_abbottabad_dec2025():
    # P I#=3030, Target for surviving infants=3339, sheet reports 91%
    pct = coverage_pct(3030, 3339)
    assert round(pct) == 91


def test_coverage_pct_handles_zero_target_without_crashing():
    assert coverage_pct(100, 0) is None


def test_coverage_pct_handles_none_target():
    assert coverage_pct(100, None) is None


def test_coverage_pct_basic_ratio():
    assert coverage_pct(50, 200) == 25.0


def test_penta_dropout_pct_matches_reported_abbottabad_dec2025():
    # P I#=3030, PIII#=2853, sheet reports Drop Out=6
    dropout = penta_dropout_pct(3030, 2853)
    assert round(dropout) == 6


def test_penta_dropout_pct_zero_when_no_dropout():
    assert penta_dropout_pct(100, 100) == 0.0


def test_penta_dropout_pct_negative_when_penta3_exceeds_penta1():
    # Real data problem case: Nawagai tehsil, Dec 2025, Drop Out reported as -42
    dropout = penta_dropout_pct(187, 203)
    assert dropout < 0


def test_penta_dropout_pct_handles_zero_penta1():
    assert penta_dropout_pct(0, 0) is None


@pytest.mark.parametrize("pct,expected", [
    (100, "good"), (COVERAGE_GOOD, "good"), (COVERAGE_GOOD - 0.01, "warning"),
    (COVERAGE_WARNING, "warning"), (COVERAGE_WARNING - 0.01, "poor"), (0, "poor"),
])
def test_coverage_rag_bands(pct, expected):
    assert coverage_rag(pct) == expected


def test_coverage_rag_none_passthrough():
    assert coverage_rag(None) is None


@pytest.mark.parametrize("pct,expected", [
    (0, "good"), (DROPOUT_GOOD, "good"), (DROPOUT_GOOD + 0.01, "warning"),
    (DROPOUT_WARNING, "warning"), (DROPOUT_WARNING + 0.01, "poor"), (99, "poor"),
])
def test_dropout_rag_bands(pct, expected):
    assert dropout_rag(pct) == expected


def test_dropout_rag_negative_value_still_bands_as_good():
    # Documented behaviour: a negative dropout is a data error, not exempted
    # from the RAG band -- it's still <= DROPOUT_GOOD so it reads 'good'.
    assert dropout_rag(-42) == "good"


def test_dropout_rag_none_passthrough():
    assert dropout_rag(None) is None
