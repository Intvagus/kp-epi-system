"""End-to-end tests against the actual Flask /generate route -- this is the
real integration point a browser upload hits, exercising detection,
independent pipeline dispatch, and the always-attempted dashboard build
together the way unit tests on the pieces individually can't.
"""
import io
import json
import re
from pathlib import Path

import pytest

from webapp.app import app as flask_app

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
DEC_FILE = RAW_DIR / "Dec 2025 Coverage Analysis (0-11).xlsx"
CUMULATIVE_FILE = RAW_DIR / "Jan to Dec 2025.xlsx"
VPD_FILE = RAW_DIR / "KP VPDs Line List Week 1-32,2026.xlsx"
WHO_FILE = RAW_DIR / "WHO_EPI_May_2024_Highlights_Dashboard.xlsx"
RCA_FILE = RAW_DIR / "RCA_Report_2.xls"
SUPERVISORY_FILE = RAW_DIR / "Supervisory_Checklist_Report.xls"
INDICATOR_SHEET_FILE = RAW_DIR / "Indicator_SheetMeasles.xlsx"
ADMIN_FILE = RAW_DIR / "Admin_Activities_Checklist.xlsx"

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


def _fetch_dashboard_data(client, resp):
    """Given the redirected /jobs/<id> response from _upload(), fetch the
    actual generated dashboard.html for that job and parse out its embedded
    DATA payload -- the same JSON the browser reads -- so a test can assert
    on real per-domain status (`"ok"` vs `"awaiting_data"`), not just on
    which download links happen to appear on the results page."""
    job_id = resp.request.path.rsplit("/", 1)[-1]
    dash_resp = client.get(f"/jobs/{job_id}/files/dashboard.html")
    assert dash_resp.status_code == 200
    match = re.search(
        rb'<script id="epi-data" type="application/json">(.*?)</script>',
        dash_resp.data, re.S,
    )
    assert match, "dashboard.html did not contain the expected embedded DATA payload"
    return json.loads(match.group(1))


def test_coverage_only_upload_builds_a_dashboard(client):
    resp = _upload(client, DEC_FILE)
    assert resp.status_code == 200
    assert b"Open dashboard.html" in resp.data
    assert b"Bulletin PDF" not in resp.data  # VPD-only artifact, correctly absent


def test_coverage_only_upload_marks_only_coverage_ok_everything_else_awaiting(client):
    """Modular-upload guarantee, checked against the actual embedded DATA
    payload the browser reads (not just which download links appear): the
    uploaded domain is "ok"; every other domain is "awaiting_data", never
    fabricated, and never silently missing from the payload."""
    resp = _upload(client, DEC_FILE)
    data = _fetch_dashboard_data(client, resp)
    assert data["coverage_summary"]["status"] == "ok"
    assert data["vpd"]["status"] == "awaiting_data"
    assert data["vpd_key_indicators"]["status"] == "awaiting_data"
    assert data["monitoring"]["rca"]["status"] == "awaiting_data"
    assert data["monitoring"]["supervisory"]["status"] == "awaiting_data"
    assert data["who_activities"]["status"] == "awaiting_data"
    assert data["admin_activities"]["status"] == "awaiting_data"


def test_cumulative_coverage_only_upload_works(client):
    """The Monthly/Cumulative pill only appears once both period types are
    present -- a Cumulative-only upload must still build a working Coverage
    section on its own, not require the Monthly file too."""
    resp = _upload(client, CUMULATIVE_FILE)
    assert resp.status_code == 200
    assert b"Open dashboard.html" in resp.data
    data = _fetch_dashboard_data(client, resp)
    assert data["coverage_summary"]["status"] == "ok"
    assert data["coverage_summary"]["periods"]["cumulative"]["status"] == "ok"
    assert data["coverage_summary"]["periods"]["monthly"]["status"] != "ok"


def test_rca_only_upload_builds_monitoring_section(client):
    resp = _upload(client, RCA_FILE)
    assert resp.status_code == 200
    assert b"Open dashboard.html" in resp.data
    data = _fetch_dashboard_data(client, resp)
    assert data["monitoring"]["rca"]["status"] == "ok"
    assert data["monitoring"]["supervisory"]["status"] == "awaiting_data"
    assert data["coverage_summary"]["status"] != "ok"


def test_supervisory_only_upload_builds_monitoring_section(client):
    resp = _upload(client, SUPERVISORY_FILE)
    assert resp.status_code == 200
    assert b"Open dashboard.html" in resp.data
    data = _fetch_dashboard_data(client, resp)
    assert data["monitoring"]["supervisory"]["status"] == "ok"
    assert data["monitoring"]["rca"]["status"] == "awaiting_data"


def test_indicator_sheet_only_upload_works(client):
    resp = _upload(client, INDICATOR_SHEET_FILE)
    assert resp.status_code == 200
    assert b"Open dashboard.html" in resp.data
    data = _fetch_dashboard_data(client, resp)
    assert data["vpd_key_indicators"]["status"] == "ok"
    assert data["vpd"]["status"] == "awaiting_data"  # the MSL line list is a separate source


def test_admin_activities_only_upload_works(client):
    resp = _upload(client, ADMIN_FILE)
    assert resp.status_code == 200
    assert b"Open dashboard.html" in resp.data
    data = _fetch_dashboard_data(client, resp)
    assert data["admin_activities"]["status"] == "ok"
    assert data["admin_activities"]["task_count"] == 19
    assert data["coverage_summary"]["status"] != "ok"
    assert data["vpd"]["status"] == "awaiting_data"


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


def test_no_auth_configured_means_no_login_required(client):
    """Default/local-dev behaviour: EPI_AUTH_USERNAME/PASSWORD unset -> every
    route works with no credentials, exactly as before this feature existed."""
    import webapp.app as webapp_module
    assert webapp_module.AUTH_ENABLED is False
    resp = client.get("/")
    assert resp.status_code == 200


def test_basic_auth_when_configured_blocks_and_allows_correctly(client, monkeypatch):
    """Opt-in HTTP Basic Auth: wrong/missing credentials are rejected, correct
    ones pass, and /healthz stays open either way (Render's health check has
    no way to supply credentials)."""
    import webapp.app as webapp_module
    monkeypatch.setattr(webapp_module, "AUTH_USERNAME", "epiuser")
    monkeypatch.setattr(webapp_module, "AUTH_PASSWORD", "epipass")
    monkeypatch.setattr(webapp_module, "AUTH_ENABLED", True)

    resp = client.get("/")
    assert resp.status_code == 401

    resp = client.get("/", headers={"Authorization": "Basic d3Jvbmc6Y3JlZHM="})  # wrong:creds
    assert resp.status_code == 401

    import base64
    good = base64.b64encode(b"epiuser:epipass").decode()
    resp = client.get("/", headers={"Authorization": f"Basic {good}"})
    assert resp.status_code == 200

    resp = client.get("/healthz")
    assert resp.status_code == 200
