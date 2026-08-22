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
from src.pipeline.run import run as run_coverage_pipeline
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
        if not name.lower().endswith(".xlsx"):
            raise ValueError(f"{f.filename!r} is not a .xlsx file.")
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

    manifest = {"errors": [], "built": {}}

    try:
        coverage_saved = _save_uploads(request.files.getlist("coverage_files"), paths["raw"])
        vpd_saved = _save_uploads(request.files.getlist("vpd_file"), paths["raw"])
    except ValueError as e:
        shutil.rmtree(paths["base"], ignore_errors=True)
        return render_template("error.html", message=str(e)), 400

    if not coverage_saved and not vpd_saved:
        shutil.rmtree(paths["base"], ignore_errors=True)
        return render_template(
            "error.html",
            message="No files were uploaded. Add at least a coverage workbook or a VPD line list.",
        ), 400

    key_messages_path = None
    key_messages_text = (request.form.get("key_messages") or "").strip()
    if key_messages_text:
        key_messages_path = paths["base"] / "key_messages.json"
        messages = [line.strip() for line in key_messages_text.splitlines() if line.strip()]
        key_messages_path.write_text(json.dumps({"messages": messages}), encoding="utf-8")

    # Coverage pipeline + dashboard (dashboard requires coverage data; VPD is optional within it)
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

    if coverage_saved and not manifest["errors"]:
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
