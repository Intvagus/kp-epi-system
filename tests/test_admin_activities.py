"""Divisional Officer & Admin Compliance tests, pinned to real values
confirmed by direct inspection of Admin_Activities_Checklist.xlsx -- a
blank per-officer administrative compliance checklist TEMPLATE (every
officer cell in the source is the literal placeholder text "Yes/No/NA",
not a real answer), not a case-level or activity-log dataset, split into
two sections by a color-coding legend the user provided in a reference
workbook. See admin_activities.py's module docstring for the full audit
finding, the user's explicit "live, fillable checklist" decision, and how
the section split was decoded.
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
    assert len(loaded["tasks"]) == 19


def test_first_and_last_task_names_match_source(loaded):
    assert loaded["tasks"][0]["task"] == "Logbook Submission"
    assert loaded["tasks"][-1]["task"] == "Other Assigned Tasks"


def test_deleted_task_is_not_present(loaded):
    """'Monthly Report Compliance' was flagged Delete (no-fill) by the
    color-coding legend the user provided and removed from the source
    workbook entirely -- must not surface anywhere in the loaded checklist."""
    task_names = {t["task"] for t in loaded["tasks"]}
    assert "Monthly Report Compliance" not in task_names


def test_renamed_travel_tasks_match_new_source(loaded):
    task_names = {t["task"] for t in loaded["tasks"]}
    assert "Travel Claims Submission" in task_names
    assert "Travel Claims Processed" in task_names
    assert "Duty Travel Requests" not in task_names
    assert "Travel Claims / Approval" not in task_names


def test_expected_evidence_descriptors_match_source(loaded):
    by_task = {t["task"]: t["expected_evidence"] for t in loaded["tasks"]}
    assert by_task["Logbook Submission"] == "Monthly"
    assert by_task["Travel Claims Submission"] == "Timely submission"
    assert by_task["Travel Claims Processed"] == "Complete documentation"
    assert by_task["Programme Section Support"] == "EPI/MNCH/Nutrition/Emergency"


def test_section_categorization_matches_color_coding_legend(loaded):
    """Decoded from the color-coding legend in the reference workbook the
    user shared (Yellow=Divisional Officer, green=Admin Section,
    magenta=Both), applied to each task row's own fill color."""
    by_task = {t["task"]: t["section"] for t in loaded["tasks"]}
    divisional = {"Logbook Submission", "Monthly Report Submission", "DSO Mobility Claims",
                  "Special Activity Reports", "Travel Claims Submission", "DDMs"}
    admin = {"Travel Claims Processed", "Training / Activity Claims", "Financial Documentation",
             "Payment Documentation", "Activity Arrangement", "Training/Workshop Coordination",
             "Stationery Management", "Courier / TCS Management", "Office Bills Processing",
             "Document Filing / Record Management", "Procurement Requests", "Programme Section Support"}
    for task in divisional:
        assert by_task[task] == "Divisional Officer", task
    for task in admin:
        assert by_task[task] == "Admin Section", task
    assert by_task["Other Assigned Tasks"] == "Both"
    assert set(by_task) == divisional | admin | {"Other Assigned Tasks"}


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
    assert summary["task_count"] == 19
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
