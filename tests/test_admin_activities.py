"""Admin Activities tests, pinned to real values confirmed by direct
inspection of Admin_Activities_Checklist.xlsx -- a blank per-officer
administrative compliance checklist TEMPLATE (every officer cell in the
source is the literal placeholder text "Yes/No/NA", not a real answer), not
a case-level or activity-log dataset. See admin_activities.py's module
docstring for the full audit finding and the user's explicit "live,
fillable checklist" decision.
"""
from pathlib import Path

import pytest

from src.pipeline.admin_activities import (
    _normalize_officer_cell, build_summary, find_admin_activities_files, load_admin_activities,
)
from src.pipeline.detect import detect_workbook_type

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
ADMIN_FILE = RAW_DIR / "Admin_Activities_Checklist.xlsx"

pytestmark = pytest.mark.skipif(
    not ADMIN_FILE.exists(),
    reason="Real Admin_Activities_Checklist.xlsx not present in this environment",
)


@pytest.fixture(scope="module")
def loaded():
    return load_admin_activities(ADMIN_FILE)


@pytest.fixture(scope="module")
def summary(loaded):
    return build_summary(loaded)


def test_detects_as_admin_activities_not_another_domain():
    result = detect_workbook_type(ADMIN_FILE)
    assert result.workbook_type == "admin_activities"


def test_find_admin_activities_files_locates_it_in_raw_dir():
    assert ADMIN_FILE in find_admin_activities_files(RAW_DIR)


def test_officer_columns_match_source(loaded):
    assert loaded["officer_labels"] == [
        "Dr Imtiaz Ali", "Dr Imran Khan", "Dr Haroon Ur Rashid",
        "Dr Kazi Taimoor", "Dr Sohrab Ali", "Dr Asad Baig",
    ]


def test_task_count_matches_source(loaded):
    assert len(loaded["tasks"]) == 20


def test_first_and_last_task_names_match_source(loaded):
    assert loaded["tasks"][0]["task"] == "Logbook Submission"
    assert loaded["tasks"][-1]["task"] == "Other Assigned Tasks"


def test_expected_evidence_descriptors_match_source(loaded):
    by_task = {t["task"]: t["expected_evidence"] for t in loaded["tasks"]}
    assert by_task["Logbook Submission"] == "Monthly"
    assert by_task["Monthly Report Compliance"] == "Quality & completeness"
    assert by_task["Programme Section Support"] == "EPI/MNCH/Nutrition/Emergency"


def test_placeholder_text_is_never_treated_as_a_real_answer(loaded):
    """Every officer cell in the source file received is the literal
    instructional string "Yes/No/NA" -- confirmed by direct inspection, not
    a real answer, so it must normalize to None (unanswered), never to a
    fabricated "Yes"/"No"/"N/A" value."""
    for task in loaded["tasks"]:
        for officer, value in task["officers"].items():
            assert value is None, f"{task['task']}/{officer} should be unanswered, got {value!r}"


def test_is_blank_template_flag_true_for_this_source(summary):
    assert summary["is_blank_template"] is True
    assert summary["prefilled_answers_count"] == 0


def test_summary_counts_match_source(summary):
    assert summary["task_count"] == 20
    assert summary["officer_count"] == 6


@pytest.mark.parametrize("raw,expected", [
    (None, None),
    ("", None),
    ("Yes/No/NA", None),
    ("Yes / No / NA", None),
    ("yes/no/na", None),
    ("Yes", "Yes"),
    ("no", "No"),
    ("N/A", "N/A"),
    ("na", "N/A"),
    ("Not Applicable", "N/A"),
    ("Partially", "Partially"),
])
def test_normalize_officer_cell(raw, expected):
    assert _normalize_officer_cell(raw) == expected
