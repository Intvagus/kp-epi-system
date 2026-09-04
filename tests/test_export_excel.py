"""export_excel.py tested against real processed output -- coverage-only,
VPD-only, both, and neither (must return None, not crash or write an empty
file), each independent of the others.
"""
import shutil
from pathlib import Path

import pandas as pd
import pytest

from src.pipeline.export_excel import build_processed_excel
from src.pipeline.run import run as run_coverage_pipeline
from src.pipeline.run_vpd import run_vpd

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
DEC_FILE = RAW_DIR / "Dec 2025 Coverage Analysis (0-11).xlsx"
VPD_FILE = RAW_DIR / "KP VPDs Line List Week 1-32,2026.xlsx"

pytestmark = pytest.mark.skipif(
    not (DEC_FILE.exists() and VPD_FILE.exists()),
    reason="Real raw Excel files not present in this environment",
)


def _prep_raw(tmp_path, files):
    raw = tmp_path / "raw"
    raw.mkdir()
    for f in files:
        shutil.copy(f, raw / f.name)
    return raw


def test_no_processed_data_returns_none_not_a_crash(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    result = build_processed_excel(processed, tmp_path / "out.xlsx")
    assert result is None
    assert not (tmp_path / "out.xlsx").exists()


def test_coverage_only_export_has_no_vpd_sheets(tmp_path):
    raw = _prep_raw(tmp_path, [DEC_FILE])
    processed = tmp_path / "processed"
    processed.mkdir()
    run_coverage_pipeline(raw_dir=raw, processed_dir=processed)

    out = build_processed_excel(processed, tmp_path / "out.xlsx")
    assert out is not None
    sheets = pd.ExcelFile(out, engine="openpyxl").sheet_names
    assert "Coverage District Data" in sheets
    assert "Coverage KPI Summary" in sheets
    assert not any("VPD" in s for s in sheets)


def test_vpd_only_export_has_no_coverage_sheets(tmp_path):
    raw = _prep_raw(tmp_path, [VPD_FILE])
    processed = tmp_path / "processed"
    processed.mkdir()
    run_vpd(raw_dir=raw, processed_dir=processed)

    out = build_processed_excel(processed, tmp_path / "out.xlsx")
    assert out is not None
    sheets = pd.ExcelFile(out, engine="openpyxl").sheet_names
    assert "VPD Surveillance Summary" in sheets
    assert not any("Coverage" in s for s in sheets)


def test_both_datasets_export_has_all_sheets(tmp_path):
    raw = _prep_raw(tmp_path, [DEC_FILE, VPD_FILE])
    processed = tmp_path / "processed"
    processed.mkdir()
    run_coverage_pipeline(raw_dir=raw, processed_dir=processed)
    run_vpd(raw_dir=raw, processed_dir=processed)

    out = build_processed_excel(processed, tmp_path / "out.xlsx")
    sheets = pd.ExcelFile(out, engine="openpyxl").sheet_names
    assert "Coverage District Data" in sheets
    assert "VPD Surveillance Summary" in sheets


def test_coverage_district_data_row_count_matches_processed_parquet(tmp_path):
    raw = _prep_raw(tmp_path, [DEC_FILE])
    processed = tmp_path / "processed"
    processed.mkdir()
    run_coverage_pipeline(raw_dir=raw, processed_dir=processed)

    out = build_processed_excel(processed, tmp_path / "out.xlsx")
    exported = pd.read_excel(out, sheet_name="Coverage District Data", engine="openpyxl")
    source = pd.read_parquet(processed / "coverage_district.parquet")
    assert len(exported) == len(source) == 37
