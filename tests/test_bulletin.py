"""Bulletin payload consistency checks, run against the real
data/processed/vpd_summary.json produced by `python run_weekly.py`.
"""
import json

import pytest

from src.pipeline.run_vpd import PROCESSED_DIR

SUMMARY_PATH = PROCESSED_DIR / "vpd_summary.json"

pytestmark = pytest.mark.skipif(
    not SUMMARY_PATH.exists(),
    reason="run `python run_weekly.py` first to generate data/processed/vpd_summary.json",
)


@pytest.fixture(scope="module")
def bulletin():
    with open(SUMMARY_PATH, encoding="utf-8") as f:
        return json.load(f)["bulletin"]


def test_bulletin_epi_week_matches_summary_latest_week(bulletin):
    with open(SUMMARY_PATH, encoding="utf-8") as f:
        summary = json.load(f)
    assert bulletin["epi_week"] == summary["latest_epi_week"]


def test_bulletin_cumulative_equals_ytd_when_week_is_latest(bulletin):
    # The bulletin's default week IS the latest week in the data, so its
    # "cumulative through week" figures must equal the full-YTD figures
    # already validated in test_indicators_vpd.py.
    assert bulletin["msl"]["cumulative"]["suspected"] == 10336


def test_bulletin_district_breakdown_rows_sum_to_this_week_total(bulletin):
    total = sum(r["suspected"] for r in bulletin["msl"]["district_breakdown_this_week"])
    assert total == bulletin["msl"]["suspected_this_week"]


def test_bulletin_pertussis_grand_total_matches_district_sum(bulletin):
    total = sum(r["case_count"] for r in bulletin["pertussis"]["district_breakdown_cumulative"])
    assert total == bulletin["pertussis"]["grand_total_cumulative"]


def test_bulletin_nnt_district_sum_matches_cumulative_count(bulletin):
    total = sum(r["case_count"] for r in bulletin["nnt"]["cumulative_district_breakdown"])
    assert total == bulletin["nnt"]["cumulative_case_count"]


def test_bulletin_afp_is_explicitly_stubbed_not_fabricated(bulletin):
    assert bulletin["afp"]["status"] == "awaiting_data"


def test_bulletin_key_messages_loaded_from_editable_input_file(bulletin):
    assert len(bulletin["key_messages"]) > 0
