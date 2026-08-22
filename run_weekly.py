"""One command: pipeline -> dashboard -> bulletin.

Runs the coverage pipeline, the VPD surveillance pipeline, builds the
dashboard HTML, then generates the bulletin (PDF + Excel annex + PPTX).
This is the one command a non-technical user runs each week after dropping
new files into data/raw/.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.bulletin.build import build as build_bulletin
from src.dashboard.build import build as build_dashboard
from src.pipeline.run import run as run_pipeline
from src.pipeline.run_vpd import run_vpd

if __name__ == "__main__":
    run_pipeline()
    vpd_summary = run_vpd()
    build_dashboard()
    if vpd_summary is not None:
        build_bulletin()
