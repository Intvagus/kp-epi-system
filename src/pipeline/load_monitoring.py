"""Read raw Monitoring domain files: RCA (Rapid Convenience Assessment,
child-level vaccination-status spot checks) and Supervisory Checklist
(facility/site-level supervisory-visit checklists).

Both are exported by the field-monitoring system as HTML tables saved with a
".xls" extension -- `file` confirms they're "HTML document", not a real
binary/OOXML workbook, so they're read with pandas.read_html, never
openpyxl. This is a different file shape from Coverage/VPD, not just a
different schema -- hence a separate loader module and a separate detection
path (see detect.py's detect_monitoring_file), rather than extending
detect_workbook_type.
"""
from pathlib import Path

import pandas as pd

from .detect import detect_monitoring_file

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def find_rca_files(raw_dir: Path | None = None) -> list[Path]:
    raw_dir = raw_dir or (PROJECT_ROOT / "data" / "raw")
    return sorted(p for p in raw_dir.glob("*.xls") if detect_monitoring_file(p).workbook_type == "rca")


def find_supervisory_files(raw_dir: Path | None = None) -> list[Path]:
    raw_dir = raw_dir or (PROJECT_ROOT / "data" / "raw")
    return sorted(p for p in raw_dir.glob("*.xls") if detect_monitoring_file(p).workbook_type == "supervisory")


def _read_html_table(path: Path) -> pd.DataFrame:
    tables = pd.read_html(path)
    if not tables:
        raise ValueError(f"{path.name} has no HTML table to read.")
    df = tables[0]
    df = df.dropna(how="all").reset_index(drop=True)
    return df


def load_rca_file(path: Path) -> pd.DataFrame:
    print(f"  Loading {path.name} (RCA child-level assessment)...")
    df = _read_html_table(path)
    print(f"    {len(df)} child assessment rows")
    return df


def load_supervisory_file(path: Path) -> pd.DataFrame:
    print(f"  Loading {path.name} (Supervisory Checklist)...")
    df = _read_html_table(path)
    print(f"    {len(df)} supervisory visit rows")
    return df
