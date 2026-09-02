"""Read the "Admin Activities" workbook -- a per-officer administrative
compliance checklist (20 fixed administrative responsibilities x 4 officer
columns, e.g. logbook/report submission, claims processing, procurement,
record management), not a case-level or activity-log dataset like every
other domain in this project.

Confirmed by direct inspection: the source file received is a BLANK
CHECKLIST TEMPLATE, not completed records. Every one of the 80
Officer-1..4 cells contains the literal instructional string "Yes/No/NA"
(telling whoever fills the sheet what to type), not an actual answer, and
the "Remarks / Evidence" column holds a fixed descriptor of what evidence
each task expects (e.g. "Monthly", "Quality & completeness"), not a real
per-period remark. There are no dates, districts, UCs, activity types, or
completed status values anywhere in the file -- confirmed by checking every
cell's value, fill color, and comments (none carry hidden data).

The user confirmed this genuinely is the intended source file and chose to
treat the Admin Activities tab as a LIVE, FILLABLE CHECKLIST inside the
dashboard (officers'/reviewers' Yes/No/N-A selections are entered and saved
in the browser, per the same localStorage-backed editable-note pattern used
elsewhere on this dashboard) rather than a chart-driven analytics tab, since
there is no completed data to chart. This module only reads the checklist's
real STRUCTURE from the workbook (task names, the 4 officer column labels,
and each task's expected-evidence descriptor) -- never the placeholder
"Yes/No/NA" text as if it were a real answer.

Forward-compatible: if a future version of this file DOES contain real
per-officer answers (a literal "Yes", "No", or "N/A", not the placeholder
phrase), _normalize_officer_cell recognizes and keeps them as genuine
source-provided starting values rather than discarding them -- see its own
docstring.
"""
import re
from pathlib import Path

import openpyxl

ADMIN_ACTIVITIES_SHEET = "Admin Activities"
TASK_COLUMN_HEADER = "Task / Administrative Responsibility"
EVIDENCE_COLUMN_HEADER = "Remarks / Evidence"

# The placeholder text a blank template cell contains, normalized (spaces/
# slashes stripped, lowercased) so "Yes/No/NA", "Yes / No / NA", etc. all
# match the same check.
_PLACEHOLDER_NORMALIZED = "yes/no/na".replace("/", "").replace(" ", "")


def _normalize_officer_cell(value):
    """None/blank -> None (unanswered). The literal placeholder phrase
    ("Yes/No/NA", however spaced) -> None (still unanswered -- it's
    instructional text, not a real answer). A genuine single-word answer
    ("Yes", "No", "NA"/"N/A", or abbreviations) -> the canonical "Yes" /
    "No" / "N/A". Anything else unrecognized is kept as-is (flagged by the
    caller via `officers_raw`), never silently dropped."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    compact = re.sub(r"[\s/]+", "", s).lower()
    if compact == _PLACEHOLDER_NORMALIZED:
        return None
    normalized = s.strip().lower()
    if normalized in {"yes", "y"}:
        return "Yes"
    if normalized in {"no", "n"}:
        return "No"
    if normalized in {"na", "n/a", "not applicable"}:
        return "N/A"
    return s


def find_admin_activities_files(raw_dir: Path) -> list[Path]:
    files = []
    for path in sorted(raw_dir.glob("*.xlsx")):
        try:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        except Exception:
            continue
        if ADMIN_ACTIVITIES_SHEET in wb.sheetnames:
            header = wb[ADMIN_ACTIVITIES_SHEET].cell(row=1, column=1).value
            if header and str(header).strip() == TASK_COLUMN_HEADER:
                files.append(path)
    return files


def load_admin_activities(path: Path) -> dict:
    """Returns the checklist's real structure -- task list, officer column
    labels, per-task expected-evidence descriptor, and any genuine
    source-provided answers (see _normalize_officer_cell). Column layout is
    read from the header row itself (never hardcoded to exactly 4 officers),
    so a future version of this file with more/fewer officer columns is
    handled without a code change."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[ADMIN_ACTIVITIES_SHEET]

    header = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    header = [str(h).strip() if h is not None else None for h in header]
    task_col = header.index(TASK_COLUMN_HEADER) + 1 if TASK_COLUMN_HEADER in header else 1
    evidence_col = header.index(EVIDENCE_COLUMN_HEADER) + 1 if EVIDENCE_COLUMN_HEADER in header else None
    officer_cols = [
        (c, header[c - 1]) for c in range(1, ws.max_column + 1)
        if c not in (task_col, evidence_col) and header[c - 1]
    ]

    tasks = []
    prefilled_count = 0
    unrecognized_count = 0
    r = 2
    while True:
        task_name = ws.cell(row=r, column=task_col).value
        if task_name is None or str(task_name).strip() == "":
            break
        officers = {}
        for col, label in officer_cols:
            raw = ws.cell(row=r, column=col).value
            value = _normalize_officer_cell(raw)
            officers[label] = value
            if value is not None:
                if value in {"Yes", "No", "N/A"}:
                    prefilled_count += 1
                else:
                    unrecognized_count += 1
        tasks.append({
            "task": str(task_name).strip(),
            "expected_evidence": (str(ws.cell(row=r, column=evidence_col).value).strip()
                                   if evidence_col and ws.cell(row=r, column=evidence_col).value else None),
            "officers": officers,
        })
        r += 1

    return {
        "source_file": path.name,
        "officer_labels": [label for _, label in officer_cols],
        "tasks": tasks,
        "prefilled_answers_count": prefilled_count,
        "unrecognized_cell_count": unrecognized_count,
    }


def build_summary(loaded: dict) -> dict:
    return {
        "status": "ok",
        "source_file": loaded["source_file"],
        "officer_labels": loaded["officer_labels"],
        "tasks": loaded["tasks"],
        "task_count": len(loaded["tasks"]),
        "officer_count": len(loaded["officer_labels"]),
        "prefilled_answers_count": loaded["prefilled_answers_count"],
        "unrecognized_cell_count": loaded["unrecognized_cell_count"],
        "is_blank_template": loaded["prefilled_answers_count"] == 0,
    }


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def run_admin_activities(raw_dir: Path | None = None, processed_dir: Path | None = None) -> dict | None:
    """Independent of every other domain -- see every other run_* entry
    point in this project for the same convention."""
    import json

    raw_dir = raw_dir or (PROJECT_ROOT / "data" / "raw")
    processed_dir = processed_dir or PROCESSED_DIR
    files = find_admin_activities_files(raw_dir)
    if not files:
        return None

    print("\nAdmin Activities pipeline starting...")
    path = files[0]
    print(f"  Loading {path.name}...")
    loaded = load_admin_activities(path)
    summary = build_summary(loaded)
    print(f"  {summary['task_count']} tasks x {summary['officer_count']} officers "
          f"({summary['prefilled_answers_count']} pre-filled answers found in source)")

    processed_dir.mkdir(parents=True, exist_ok=True)
    with open(processed_dir / "admin_activities_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print("Admin Activities pipeline finished OK.")
    return summary
