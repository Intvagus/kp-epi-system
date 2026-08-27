"""Content-based classification of an uploaded .xlsx workbook: Coverage,
VPD surveillance, or unrecognized -- by comparing its actual sheet names
against the two known signatures, never by filename convention.

Filename sniffing (the old approach: "vpd" in the filename means VPD, else
assume coverage) breaks the moment a real upload isn't named the way this
project's own sample files happen to be named. Sheet names are the one thing
both source files actually guarantee, per CLAUDE.md's confirmed structure.

Monitoring/supervisory-visit data has no known signature here on purpose --
no sample file has ever been received (see CLAUDE.md's open questions), so
there is nothing to detect against. A workbook that isn't a Coverage or VPD
match falls out as "unknown" with an honest message, never guessed at.
"""
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .config import SHEET_NAMES, VPD_SHEET_NAMES

COVERAGE_SIGNATURE = {name.strip().lower() for name in SHEET_NAMES.values()}
VPD_SIGNATURE = {name.strip().lower() for name in VPD_SHEET_NAMES.values()}

# A workbook doesn't need every expected sheet to match (e.g. a re-export
# missing one sheet) -- this many of the signature's sheet names present is
# enough to call it confidently, while still ruling out a coincidental
# single-sheet-name overlap with an unrelated file.
MIN_MATCHING_SHEETS = 2


@dataclass
class DetectionResult:
    workbook_type: str  # "coverage" | "vpd" | "unknown" | "empty" | "unreadable"
    matched_sheets: list = field(default_factory=list)
    all_sheets: list = field(default_factory=list)
    message: str = ""


def _sheet_names(path: Path) -> list[str]:
    return pd.ExcelFile(path, engine="openpyxl").sheet_names


def detect_workbook_type(path: Path) -> DetectionResult:
    """Classify one .xlsx by its actual sheet names."""
    try:
        sheets = _sheet_names(path)
    except Exception as e:
        return DetectionResult(
            "unreadable", [], [],
            f"{path.name!r} could not be opened as an Excel file ({e}). "
            f"Confirm it's a real, uncorrupted .xlsx workbook."
        )

    if not sheets:
        return DetectionResult("empty", [], [], f"{path.name!r} has no sheets -- it appears to be empty.")

    normalized = {s.strip().lower(): s for s in sheets}
    coverage_matches = [normalized[k] for k in normalized if k in COVERAGE_SIGNATURE]
    vpd_matches = [normalized[k] for k in normalized if k in VPD_SIGNATURE]

    if len(coverage_matches) >= MIN_MATCHING_SHEETS and len(coverage_matches) >= len(vpd_matches):
        return DetectionResult(
            "coverage", coverage_matches, sheets,
            f"Recognized as a Coverage workbook ({len(coverage_matches)} of "
            f"{len(COVERAGE_SIGNATURE)} expected sheets found)."
        )
    if len(vpd_matches) >= MIN_MATCHING_SHEETS:
        return DetectionResult(
            "vpd", vpd_matches, sheets,
            f"Recognized as a VPD surveillance line list ({len(vpd_matches)} of "
            f"{len(VPD_SIGNATURE)} expected sheets found)."
        )
    shown = ", ".join(sheets[:6]) + (", ..." if len(sheets) > 6 else "")
    return DetectionResult(
        "unknown", [], sheets,
        f"Could not confidently identify {path.name!r} as a Coverage or VPD surveillance "
        f"workbook from its sheet names ({shown}). Monitoring/supervisory-visit uploads "
        f"aren't supported yet -- no sample file has been received to build that pipeline "
        f"against. If this is meant to be a Coverage or VPD file with renamed sheets, "
        f"rename them to match the expected sheet names and re-upload."
    )
