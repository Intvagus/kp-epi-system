"""End-to-end tests against the actual Flask /generate route -- this is the
real integration point a browser upload hits, exercising detection,
independent pipeline dispatch, and the always-attempted dashboard build
together the way unit tests on the pieces individually can't.
"""
import io
from pathlib import Path

import pytest

from webapp.app import app as flask_app

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
DEC_FILE = RAW_DIR / "Dec 2025 Coverage Analysis (0-11).xlsx"
VPD_FILE = RAW_DIR / "KP VPDs Line List Week 1-32,2026.xlsx"
WHO_FILE = RAW_DIR / "WHO_EPI_May_2024_Highlights_Dashboard.xlsx"

pytestmark = pytest.mark.skipif(
    not (DEC_FILE.exists() and VPD_FILE.exists()),
    reason="Real raw Excel files not present in this environment",
)


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def _upload(client, *file_paths):
    data = {"files": [(io.BytesIO(p.read_bytes()), p.name) for p in file_paths]}
    return client.post("/generate", data=data, content_type="multipart/form-data", follow_redirects=True)


def test_coverage_only_upload_builds_a_dashboard(client):
    resp = _upload(client, DEC_FILE)
    assert resp.status_code == 200
    assert b"Open dashboard.html" in resp.data
    assert b"Bulletin PDF" not in resp.data  # VPD-only artifact, correctly absent


def test_vpd_only_upload_builds_a_dashboard_and_bulletin(client):
    # This is the exact bug fixed this session: a VPD-only upload used to
    # build a bulletin but NO dashboard at all, because the dashboard build
    # was gated behind a coverage file being present.
    resp = _upload(client, VPD_FILE)
    assert resp.status_code == 200
    assert b"Open dashboard.html" in resp.data
    assert b"Bulletin PDF" in resp.data


def test_both_files_uploaded_in_either_slot_still_work(client):
    # Both files go through the single generic "files" field now -- content
    # detection must correctly route each regardless of upload order.
    resp = _upload(client, VPD_FILE, DEC_FILE)
    assert resp.status_code == 200
    assert b"Open dashboard.html" in resp.data
    assert b"Bulletin PDF" in resp.data


def test_who_activities_only_upload_builds_a_dashboard(client):
    resp = _upload(client, WHO_FILE)
    assert resp.status_code == 200
    assert b"Open dashboard.html" in resp.data
    assert b"Bulletin PDF" not in resp.data  # VPD-only artifact, correctly absent


def test_unrecognized_file_does_not_block_the_recognized_one(client, tmp_path):
    import openpyxl
    junk_path = tmp_path / "unrelated_report.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "Random Sheet"
    wb.save(junk_path)

    resp = _upload(client, DEC_FILE, junk_path)
    assert resp.status_code == 200
    assert b"Open dashboard.html" in resp.data  # the good file still worked
    assert b"unrelated_report.xlsx" in resp.data  # the bad one is reported, not silent

    junk_path.unlink()


def test_no_files_uploaded_is_a_clear_error_not_a_crash(client):
    resp = client.post("/generate", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert b"No files were uploaded" in resp.data


def test_excel_data_export_is_built(client):
    resp = _upload(client, DEC_FILE)
    assert resp.status_code == 200
    assert b"EPI_Data_Export.xlsx" in resp.data
