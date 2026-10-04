"""Regression tests for two real bugs found from live user uploads (2026-10):

1. results.html's "What we found in your upload" badge only had explicit
   branches for "coverage"/"vpd" -- every other correctly-recognized type
   (rca, supervisory, indicator_sheet, who_activities, admin_activities)
   fell into the catch-all "not recognized" (red) branch even though it
   processed successfully, which would badly confuse a non-technical user
   into thinking a working upload had failed.

2. webapp/app.py embedded raw Python tracebacks (traceback.format_exc) into
   the user-facing Notices box on any unexpected pipeline failure -- fixed
   to log the traceback server-side only and show a short, plain-language
   message instead (_log_unexpected_error).

Uses small synthetic workbooks built inline (not the real sample files in
data/raw/, which may not be present in every environment) so these tests
run unconditionally.
"""
import io

import openpyxl
import pytest

from webapp.app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def _xlsx_bytes(build_fn) -> bytes:
    wb = openpyxl.Workbook()
    build_fn(wb)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def _admin_activities_workbook() -> bytes:
    def build(wb):
        wb.remove(wb.active)
        ws = wb.create_sheet("Admin Activities")
        ws.cell(row=1, column=1, value="Task / Administrative Responsibility")
        ws.cell(row=1, column=2, value="Officer 1")
        ws.cell(row=2, column=1, value="Logbook Submission")
        ws.cell(row=2, column=2, value="Yes/No/NA")
    return _xlsx_bytes(build)


@pytest.mark.parametrize("expected_label", [
    "Admin Activities Checklist",
])
def test_admin_activities_upload_shows_recognized_label_not_not_recognized(client, expected_label):
    data = {"files": [(io.BytesIO(_admin_activities_workbook()), "Admin_Activities_Checklist.xlsx")]}
    resp = client.post("/generate", data=data, content_type="multipart/form-data", follow_redirects=True)
    body = resp.data.decode()
    assert expected_label in body
    # The old bug rendered this exact type as the red catch-all -- assert
    # the catch-all text is nowhere near this file's own detected-type line.
    found_idx = body.find("Admin_Activities_Checklist.xlsx")
    assert found_idx != -1
    nearby = body[found_idx:found_idx + 400]
    assert "not recognized" not in nearby


def test_unexpected_pipeline_failure_shows_friendly_message_not_a_traceback(client, monkeypatch):
    """Force an unexpected (non-SystemExit) exception inside the Coverage
    pipeline call and confirm the results page shows the friendly
    _log_unexpected_error() message, never a raw Python traceback."""
    import webapp.app as webapp_module

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated unexpected pipeline crash")

    monkeypatch.setattr(webapp_module, "run_coverage_pipeline", _boom)

    def build(wb):
        wb.remove(wb.active)
        for name in ["District ", "Teshil ", "UC Wise Analysis - Coverages", "UC Wise Analysis - Difference i"]:
            wb.create_sheet(name)
    data = {"files": [(io.BytesIO(_xlsx_bytes(build)), "March 2026 Coverage Analysis.xlsx")]}
    resp = client.post("/generate", data=data, content_type="multipart/form-data", follow_redirects=True)
    body = resp.data.decode()

    assert "Traceback" not in body
    assert "RuntimeError" not in body
    assert "File &#34;/" not in body  # no raw Python file-path frames leaked into the HTML
    assert "Problem processing your Coverage file" in body
    assert "something unexpected went wrong" in body


def test_run_pipeline_preserves_real_error_message_not_bare_exit_code(tmp_path):
    """Regression test for the exact bug the user hit live: run.py used to
    do `raise SystemExit(1) from e`, discarding the real underlying message
    and leaving only the bare string "1" for the webapp to show -- e.g. the
    live user-facing Notices box literally read "Coverage pipeline: 1".
    Forces a real load failure (a coverage-detected workbook missing its
    required sheets) and asserts the raised SystemExit's message is the
    real, actionable explanation, not just "1"."""
    import openpyxl

    from src.pipeline.run import run

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    # Matches enough of the coverage signature to be detected as "coverage"
    # (detect.py's MIN_MATCHING_SHEETS=2) but is missing the District/Teshil
    # sheets load_workbook() actually needs -- a real, plausible failure
    # mode (e.g. someone renames or deletes a tab by mistake).
    wb.create_sheet("UC Wise Analysis - Coverages")
    wb.create_sheet("UC Wise Analysis - Difference i")
    wb.save(raw_dir / "March 2026 Coverage Analysis.xlsx")

    with pytest.raises(SystemExit) as excinfo:
        run(raw_dir=raw_dir, processed_dir=tmp_path / "processed")

    message = str(excinfo.value)
    assert message != "1"
    assert "District" in message or "Teshil" in message


def test_dashboard_build_failure_uses_non_file_phrasing(client, monkeypatch):
    """The dashboard/bulletin build steps aren't a specific uploaded file --
    confirm they get "the dashboard build" phrasing, not the misleading
    "your dashboard build file" wording a naive fix could have produced."""
    import webapp.app as webapp_module

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated dashboard build crash")

    monkeypatch.setattr(webapp_module, "build_dashboard", _boom)

    def build(wb):
        wb.remove(wb.active)
        for name in ["District ", "Teshil ", "UC Wise Analysis - Coverages", "UC Wise Analysis - Difference i"]:
            wb.create_sheet(name)
    data = {"files": [(io.BytesIO(_xlsx_bytes(build)), "March 2026 Coverage Analysis.xlsx")]}
    resp = client.post("/generate", data=data, content_type="multipart/form-data", follow_redirects=True)
    body = resp.data.decode()

    assert "Traceback" not in body
    assert "Problem processing the dashboard build" in body
    assert "your dashboard build file" not in body
