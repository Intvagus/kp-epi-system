"""Web front end for the EPI pipeline: upload Excel files, get back the
dashboard and bulletin. Wraps the exact same src/pipeline, src/dashboard and
src/bulletin modules the CLI (run_weekly.py) uses -- this file adds no new
data logic of its own, only file handling and per-job isolation.

Each upload gets its own temp directory (data/raw, data/processed, output)
so concurrent users never see each other's files. No login is required (by
the project owner's explicit choice) -- job IDs are random UUIDs so results
aren't guessable/enumerable, which is the only isolation in place; treat any
URL as knowable by whoever has the link.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
import uuid
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.bulletin.build import build as build_bulletin
from src.dashboard.build import build as build_dashboard
from src.pipeline.admin_activities import run_admin_activities
from src.pipeline.detect import detect_monitoring_file, detect_workbook_type
from src.pipeline.export_excel import build_processed_excel
from src.pipeline.indicator_sheet_vpd import run_indicator_sheet
from src.pipeline.who_activities import run_who_activities
from src.pipeline.run import run as run_coverage_pipeline
from src.pipeline.run_monitoring import run_monitoring
from src.pipeline.run_vpd import run_vpd

JOBS_ROOT = Path(tempfile.gettempdir()) / "epi_jobs"
JOB_MAX_AGE_SECONDS = 24 * 3600  # jobs older than this get swept on the next upload

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024  # 60 MB total upload cap


def _job_paths(job_id: str) -> dict:
    base = JOBS_ROOT / job_id
    return {
        "base": base,
        "raw": base / "data" / "raw",
        "processed": base / "data" / "processed",
        "output": base / "output",
        "manifest": base / "manifest.json",
    }


def _sweep_old_jobs():
    if not JOBS_ROOT.exists():
        return
    now = time.time()
    for child in JOBS_ROOT.iterdir():
        try:
            if child.is_dir() and (now - child.stat().st_mtime) > JOB_MAX_AGE_SECONDS:
                shutil.rmtree(child, ignore_errors=True)
        except OSError:
            pass


def _safe_upload_name(filename: str) -> str:
    """Strip any directory component and reject path traversal, but
    otherwise preserve the filename as-is -- unlike werkzeug's
    secure_filename(), which replaces spaces/parentheses with underscores
    and would silently break period-inference (src/pipeline/config.py's
    regexes expect the exact source filenames, e.g. 'Dec 2025 Coverage
    Analysis (0-11).xlsx')."""
    name = os.path.basename(filename.replace("\\", "/"))
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise ValueError(f"Invalid filename: {filename!r}")
    return name


def _save_uploads(files, dest_dir: Path):
    dest_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        if not f or not f.filename:
            continue
        name = _safe_upload_name(f.filename)
        if not name.lower().endswith((".xlsx", ".xls")):
            raise ValueError(f"{f.filename!r} is not a .xlsx or .xls file.")
        f.save(dest_dir / name)
        saved.append(name)
    return saved


@app.route("/")
def index():
    _sweep_old_jobs()
    return render_template("upload.html")


@app.route("/generate", methods=["POST"])
def generate():
    job_id = uuid.uuid4().hex
    paths = _job_paths(job_id)
    paths["raw"].mkdir(parents=True, exist_ok=True)

    manifest = {"errors": [], "built": {}, "detected": []}

    try:
        saved = _save_uploads(request.files.getlist("files"), paths["raw"])
    except ValueError as e:
        shutil.rmtree(paths["base"], ignore_errors=True)
        return render_template("error.html", message=str(e)), 400

    if not saved:
        shutil.rmtree(paths["base"], ignore_errors=True)
        return render_template(
            "error.html",
            message="No files were uploaded. Add at least one .xlsx or .xls file (Coverage, "
                    "VPD surveillance, RCA, and/or Supervisory Checklist -- each is detected "
                    "automatically, none is mandatory).",
        ), 400

    # Classify every uploaded file by its actual content, never by filename --
    # see src/pipeline/detect.py. Coverage/VPD are real .xlsx workbooks
    # classified by sheet name; RCA/Supervisory Checklist are ".xls" files
    # that are actually HTML tables, classified by column name instead (a
    # genuinely different file shape, not just a different schema). Each
    # file is routed to whatever pipeline it belongs to; a file that can't be
    # confidently identified is reported clearly rather than silently
    # dropped or guessed at, and never blocks the files that WERE recognized.
    coverage_saved, vpd_saved, rca_saved, supervisory_saved, indicator_sheet_saved, who_activities_saved, admin_activities_saved = [], [], [], [], [], [], []
    for name in saved:
        path = paths["raw"] / name
        result = detect_monitoring_file(path) if name.lower().endswith(".xls") else detect_workbook_type(path)
        manifest["detected"].append({"filename": name, "type": result.workbook_type, "message": result.message})
        if result.workbook_type == "coverage":
            coverage_saved.append(name)
        elif result.workbook_type == "vpd":
            vpd_saved.append(name)
        elif result.workbook_type == "rca":
            rca_saved.append(name)
        elif result.workbook_type == "supervisory":
            supervisory_saved.append(name)
        elif result.workbook_type == "indicator_sheet":
            indicator_sheet_saved.append(name)
        elif result.workbook_type == "who_activities":
            who_activities_saved.append(name)
        elif result.workbook_type == "admin_activities":
            admin_activities_saved.append(name)
        else:
            manifest["errors"].append(f"{name}: {result.message}")

    key_messages_path = None
    key_messages_text = (request.form.get("key_messages") or "").strip()
    if key_messages_text:
        key_messages_path = paths["base"] / "key_messages.json"
        messages = [line.strip() for line in key_messages_text.splitlines() if line.strip()]
        key_messages_path.write_text(json.dumps({"messages": messages}), encoding="utf-8")

    # Coverage and VPD are independent modules -- each pipeline only runs if
    # its own dataset was actually detected, and a problem in one never stops
    # the other from processing or the dashboard from including what did work.
    if coverage_saved:
        try:
            run_coverage_pipeline(raw_dir=paths["raw"], processed_dir=paths["processed"])
        except SystemExit as e:
            manifest["errors"].append(f"Coverage pipeline: {e}")
        except Exception:
            manifest["errors"].append("Coverage pipeline: unexpected failure -- " + traceback.format_exc(limit=2))

    vpd_summary = None
    if vpd_saved:
        try:
            vpd_summary = run_vpd(raw_dir=paths["raw"], processed_dir=paths["processed"],
                                   key_messages_path=key_messages_path)
        except SystemExit as e:
            manifest["errors"].append(f"VPD pipeline: {e}")
        except Exception:
            manifest["errors"].append("VPD pipeline: unexpected failure -- " + traceback.format_exc(limit=2))

    # RCA and Supervisory Checklist are independent of each other too -- an
    # RCA-only or Supervisory-only upload still builds a Monitoring tab, and
    # of Coverage/VPD (a Monitoring upload with neither of those still works).
    if rca_saved or supervisory_saved:
        try:
            run_monitoring(raw_dir=paths["raw"], processed_dir=paths["processed"])
        except SystemExit as e:
            manifest["errors"].append(f"Monitoring pipeline: {e}")
        except Exception:
            manifest["errors"].append("Monitoring pipeline: unexpected failure -- " + traceback.format_exc(limit=2))

    # Independent of every other pipeline -- an Indicator Sheet upload with
    # no line list (or vice versa) still works.
    if indicator_sheet_saved:
        try:
            run_indicator_sheet(raw_dir=paths["raw"], processed_dir=paths["processed"])
        except Exception:
            manifest["errors"].append("Indicator Sheet pipeline: unexpected failure -- " + traceback.format_exc(limit=2))

    if who_activities_saved:
        try:
            run_who_activities(raw_dir=paths["raw"], processed_dir=paths["processed"])
        except Exception:
            manifest["errors"].append("WHO Supported Activities pipeline: unexpected failure -- " + traceback.format_exc(limit=2))

    if admin_activities_saved:
        try:
            run_admin_activities(raw_dir=paths["raw"], processed_dir=paths["processed"])
        except Exception:
            manifest["errors"].append("Admin Activities pipeline: unexpected failure -- " + traceback.format_exc(limit=2))

    # Always attempted, regardless of which pipelines ran or failed above --
    # build_dashboard degrades each tab independently (an "awaiting data"
    # state for whatever component wasn't uploaded/didn't process), so a
    # Coverage-only or VPD-only job still gets a fully working dashboard.
    try:
        build_dashboard(processed_dir=paths["processed"], output_path=paths["output"] / "dashboard.html")
        manifest["built"]["dashboard"] = "dashboard.html"
    except SystemExit as e:
        manifest["errors"].append(f"Dashboard build: {e}")
    except Exception:
        manifest["errors"].append("Dashboard build: unexpected failure -- " + traceback.format_exc(limit=2))

    if vpd_saved and vpd_summary is not None:
        try:
            build_bulletin(processed_dir=paths["processed"], output_dir=paths["output"])
            week, year = vpd_summary["bulletin"]["epi_week"], vpd_summary["bulletin"]["year"]
            manifest["built"]["bulletin_pdf"] = f"Bulletin_Week_{week}_{year}.pdf"
            manifest["built"]["bulletin_xlsx"] = f"Bulletin_Week_{week}_{year}_annex.xlsx"
            manifest["built"]["bulletin_pptx"] = f"Bulletin_Week_{week}_{year}.pptx"
        except SystemExit as e:
            manifest["errors"].append(f"Bulletin build: {e}")
        except Exception:
            manifest["errors"].append("Bulletin build: unexpected failure -- " + traceback.format_exc(limit=2))
    elif coverage_saved and not vpd_saved:
        manifest["errors"].append(
            "No VPD file was uploaded, so no bulletin was generated (the bulletin is VPD-only). "
            "The dashboard's Surveillance tab shows 'awaiting data' instead of fabricated numbers."
        )

    # Multi-sheet Excel export of whatever processed data exists -- built
    # from the same processed_dir the dashboard reads, so it can never show
    # different numbers. Only includes sheets for components that actually
    # processed; never a hard requirement like the dashboard.
    try:
        excel_path = build_processed_excel(processed_dir=paths["processed"],
                                            output_path=paths["output"] / "EPI_Data_Export.xlsx")
        if excel_path is not None:
            manifest["built"]["data_export_xlsx"] = excel_path.name
    except Exception:
        manifest["errors"].append("Data export (Excel): unexpected failure -- " + traceback.format_exc(limit=2))

    paths["manifest"].write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return redirect(url_for("job_results", job_id=job_id))


@app.route("/jobs/<job_id>")
def job_results(job_id):
    paths = _job_paths(job_id)
    if not paths["manifest"].exists():
        abort(404)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    return render_template("results.html", job_id=job_id, manifest=manifest)


@app.route("/jobs/<job_id>/files/<path:filename>")
def job_file(job_id, filename):
    paths = _job_paths(job_id)
    file_path = (paths["output"] / secure_filename(filename)).resolve()
    if not str(file_path).startswith(str(paths["output"].resolve())) or not file_path.exists():
        abort(404)
    as_attachment = not filename.endswith((".html", ".pdf"))
    return send_file(file_path, as_attachment=as_attachment)


@app.route("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
