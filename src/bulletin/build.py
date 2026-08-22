"""Builds Bulletin_Week_<N>_<year>.pdf from data/processed/vpd_summary.json's
'bulletin' section -- never touches data/raw/ or recomputes an indicator.
Same Chart.js bundle as the dashboard (src/dashboard/chart.umd.min.js),
reused rather than duplicated.
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BULLETIN_DIR = Path(__file__).resolve().parent
CHARTJS_PATH = PROJECT_ROOT / "src" / "dashboard" / "chart.umd.min.js"


def load_bulletin_data(processed_dir: Path) -> dict:
    path = processed_dir / "vpd_summary.json"
    if not path.exists():
        raise SystemExit(
            f"Missing {path}. Run the VPD pipeline first to generate processed VPD data "
            f"-- the bulletin needs a VPD line list, there's nothing to build without one."
        )
    with open(path, encoding="utf-8") as f:
        summary = json.load(f)
    if "bulletin" not in summary:
        raise SystemExit(f"{path} has no 'bulletin' section. Re-run the VPD pipeline to regenerate it.")
    return summary["bulletin"]


def render_html(bulletin: dict) -> str:
    payload_json = json.dumps(bulletin, default=str, separators=(",", ":"))
    chartjs_source = CHARTJS_PATH.read_text(encoding="utf-8")
    template = (BULLETIN_DIR / "template.html").read_text(encoding="utf-8")
    return (
        template
        .replace("/*__CHARTJS_SOURCE__*/", chartjs_source)
        .replace("/*__BULLETIN_DATA_JSON__*/", payload_json)
    )


def build_pdf(bulletin: dict, output_dir: Path) -> Path:
    from playwright.sync_api import sync_playwright

    html = render_html(bulletin)
    output_dir.mkdir(parents=True, exist_ok=True)
    html_tmp = output_dir / "_bulletin_render.html"
    html_tmp.write_text(html, encoding="utf-8")

    out_path = output_dir / f"Bulletin_Week_{bulletin['epi_week']}_{bulletin['year']}.pdf"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html_tmp.as_uri())
        page.wait_for_function("window.__CHARTS_READY__ === true", timeout=10000)
        page.wait_for_timeout(150)  # let Chart.js finish its paint after the flag flips
        page.pdf(path=str(out_path), format="A4", print_background=True,
                 margin={"top": "0mm", "bottom": "0mm", "left": "0mm", "right": "0mm"})
        browser.close()

    html_tmp.unlink()
    return out_path


def build(processed_dir: Path | None = None, output_dir: Path | None = None):
    """`processed_dir`/`output_dir` default to this project's data/processed
    and output/; the web app passes per-job temp paths instead."""
    from .exports import build_excel_annex, build_pptx

    processed_dir = processed_dir or (PROJECT_ROOT / "data" / "processed")
    output_dir = output_dir or (PROJECT_ROOT / "output")

    print("Building bulletin...")
    bulletin = load_bulletin_data(processed_dir)
    print(f"  Rendering {bulletin['week_label']} ({bulletin['cumulative_label']} cumulative)...")

    pdf_path = build_pdf(bulletin, output_dir)
    print(f"  Wrote {pdf_path} ({pdf_path.stat().st_size / 1024:.0f} KB)")

    xlsx_path = build_excel_annex(bulletin, output_dir)
    print(f"  Wrote {xlsx_path} ({xlsx_path.stat().st_size / 1024:.0f} KB)")

    pptx_path = build_pptx(bulletin, output_dir)
    print(f"  Wrote {pptx_path} ({pptx_path.stat().st_size / 1024:.0f} KB)")

    print("Bulletin build finished OK.")
    return pdf_path


if __name__ == "__main__":
    try:
        build()
    except SystemExit as e:
        print(e, file=sys.stderr)
        sys.exit(1)
