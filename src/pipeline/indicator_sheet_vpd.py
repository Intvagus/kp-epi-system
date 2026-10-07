"""Read the "Measles Indicator Sheet" workbook -- a separate, real .xlsx
export (not the HTML-table Monitoring files) containing one sheet per year,
each a per-district table of measles/rubella surveillance performance
indicators plus a "Provincial Total" row. Distinct from the MSL line list
(KP VPDs Line List Week N-N,YYYY.xlsx): the line list is case-level raw
data, this sheet is the source system's own pre-aggregated indicator
report, with a different (much smaller) district total than the line list's
weekly-cumulative count -- the two are never reconciled against each other,
only shown side by side.

Column layout (row 2 = header, row 3 = sub-header for the G:K "Measles
Cases" group, data from row 4, "Provincial Total" as the last data row) is
confirmed via direct inspection of the source workbook's cell fills: columns
F, L, N, P, Q, S are highlighted a distinct color in the source (rate/%
indicators) vs. B/C/D/E/G-K/M/O/R (raw counts) -- those 6 highlighted
columns are the "key indicators" this module surfaces, never invented.
"""
import json
import re
from pathlib import Path

import openpyxl

INDICATOR_SHEET_TITLE_MARKER = "indicator sheet"
_YEAR_IN_TITLE_RE = re.compile(r"(20\d{2})")

# This workbook spells district names differently from the Coverage/
# Monitoring files (its own data-entry convention, confirmed by direct
# inspection -- e.g. "Bajour" not "Bajaur", "D I Khan" not "D.I. Khan").
# Maps every one of its 37 district rows (36 real + "Torghar", matching
# DISTRICT_TO_BOUNDARY's 36 keys plus the real Tor Ghar district that has no
# Coverage-file data) to this project's canonical spelling, so the incidence
# map can share the same kp_districts.geojson boundaries as every other map.
# "South Wazirisan Upper"/"South Waziristan Lower" -> SW Wazir Belt/SW
# Mehsud Belt carries the same Upper=Wazir/Lower=Mehsud assumption flagged in
# config.DISTRICT_TO_BOUNDARY -- this sheet's own Upper/Lower naming is a
# second, independent data point consistent with that assumption, not proof.
DISTRICT_NAME_CANONICAL = {
    "Abbottabad": "Abbottabad", "Bajour": "Bajaur", "Bannu": "Bannu",
    "Battagram": "Battagram", "Buner": "Buner", "Charssada": "Charsadda",
    "Chitral Lower": "Chitral Lower", "Chitral Upper": "Chitral Upper",
    "D I Khan": "D.I. Khan", "Dir Lower": "Dir Lower", "Dir Upper": "Dir Upper",
    "Hangu": "Hangu", "Haripur": "Haripur", "Karak": "Karak", "Khyber": "Khyber",
    "Kohat": "Kohat", "Kohistan Lower": "Kohistan Lower", "Kohistan Upper": "Kohistan Upper",
    "Kolai Palas": "Kolai Palas Kohistan", "Kurram L&C": "Kurram Lower and Central",
    "Kurram Upper": "Kurram Upper", "Lakki Marwat": "Lakki Marwat", "Malakand": "Malakand",
    "Mansehra": "Mansehra", "Mardan": "Mardan", "Mohmand": "Mohmand",
    "North Waziristan": "North Waziristan", "Nowshera": "Nowshera", "Orakzai": "Orakzai",
    "Peshawar": "Peshawar", "Shangla": "Shangla",
    "South Wazirisan Upper": "SW Wazir Belt", "South Waziristan Lower": "SW Mehsud Belt",
    "Swabi": "Swabi", "Swat": "Swat", "Tank": "Tank", "Torghar": "Tor Ghar",
    # "KP Kohistan" appears in a newer "Master Sheet" export (2026-10) in
    # place of "Kolai Palas" -- confirmed with the user to be the same
    # district under a different abbreviation, not a new entity.
    "KP Kohistan": "Kolai Palas Kohistan",
}

# WHO-standard measles incidence bands (cases per million population,
# annualized -- this sheet's own "measles_incidence_per_million" column is
# already an annualized rate, confirmed by its column header). Fixed
# thresholds, not derived from the data.
INCIDENCE_BANDS = [
    (5, "green", "Low (<5)"),
    (20, "yellow", "Moderate (5 to <20)"),
    (None, "red", "Disruptive outbreak (≥20)"),
]


def _incidence_band(value):
    if value is None:
        return None
    for upper, color, label in INCIDENCE_BANDS:
        if upper is None or value < upper:
            return {"color": color, "label": label}
    return None

# Fixed column positions (1-indexed), confirmed against the real workbook --
# not name-based, since the header text has trailing whitespace / minor
# year-to-year wording drift ("% Sample Collected" vs "% Sampling").
COLUMNS = {
    "district": 1, "total_population": 2, "minimum_expected_cases": 3,
    "total_cases_reported": 4, "non_measles_non_rubella_cases": 5,
    "non_measles_non_rubella_rate": 6,
    "measles_lab_confirmed": 7, "measles_double_infection": 8,
    "measles_epi_linked": 9, "measles_clinically_compatible": 10, "measles_total": 11,
    "measles_incidence_per_million": 12, "rubella_confirmed_cases": 13,
    "rubella_incidence_per_million": 14, "pending_classification": 15,
    "pct_sample_collected": 16, "pct_adequate_investigation": 17,
    "total_deaths": 18, "measles_related_deaths": 19,
}
HEADER_ROW = 2  # historical default; _select_year_sheet now detects this per-sheet, see below
DATA_START_ROW = 4  # historical default; load_indicator_sheet computes this from the detected header row instead
PROVINCIAL_TOTAL_LABEL = "Provincial Total"
# A newer "Master Sheet" export (2026-10) labels this row just "Provincial" --
# matched case/whitespace-insensitively, same tolerance already used for
# sheet-name drift elsewhere in this project (see sheet_utils.py).
PROVINCIAL_TOTAL_LABELS = {"provincial total", "provincial"}

# The 6 columns confirmed highlighted in the source (a distinct fill color
# from every other column) -- the sheet author's own designation of which
# indicators matter most, not a selection made in this codebase.
KEY_INDICATORS = [
    {"key": "non_measles_non_rubella_rate", "label": "Non-Measles/Non-Rubella (Discard) Rate",
     "unit": "per 100,000 population (annualized)", "decimals": 1},
    {"key": "measles_incidence_per_million", "label": "Measles Incidence",
     "unit": "per million population (annualized)", "decimals": 1},
    {"key": "rubella_incidence_per_million", "label": "Rubella Incidence",
     "unit": "per million population", "decimals": 1},
    {"key": "pct_sample_collected", "label": "Sample Collection",
     "unit": "% of cases", "decimals": 1},
    {"key": "pct_adequate_investigation", "label": "Adequate Investigation",
     "unit": "% of cases", "decimals": 1},
    {"key": "measles_related_deaths", "label": "Measles-Related Deaths",
     "unit": "count", "decimals": 0},
]


def find_indicator_sheet_files(raw_dir: Path) -> list[Path]:
    files = []
    for path in sorted(raw_dir.glob("*.xlsx")):
        try:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        except Exception:
            continue
        for name in wb.sheetnames:
            title = wb[name].cell(row=1, column=1).value
            if title and INDICATOR_SHEET_TITLE_MARKER in str(title).strip().lower():
                files.append(path)
                break
    return files


def _find_header_row(ws, max_scan_rows: int = 6) -> int | None:
    """Locate the real header row (column A == 'District', column B mentions
    'population') by scanning the first few rows, rather than assuming a
    fixed row number -- a newer export (2026-10) has one extra blank row
    after the title, shifting the header (and everything below it) down by
    one from the historical row-2 convention."""
    for row in range(1, max_scan_rows + 1):
        district_cell = str(ws.cell(row=row, column=COLUMNS["district"]).value or "").strip().lower()
        population_cell = str(ws.cell(row=row, column=COLUMNS["total_population"]).value or "").lower()
        if district_cell == "district" and "population" in population_cell:
            return row
    return None


def _select_year_sheet(wb) -> tuple[str, object, int]:
    """Pick the Indicator Sheet data to read and the row its real header
    actually starts on. Prefers a sheet literally named a bare year (the
    original convention, most recent year first); falls back to any sheet
    carrying the Indicator Sheet's own A1 title marker (a newer export names
    the sheet descriptively instead, e.g. "Measles Indicator Sheet", with the
    year only inside the title text) -- structural validation (the header
    row must actually be found) decides usability in both cases, not just
    the sheet/name existing."""
    year_sheets = sorted((n for n in wb.sheetnames if n.strip().isdigit()), reverse=True)
    for name in year_sheets:
        header_row = _find_header_row(wb[name])
        if header_row is not None:
            return name, wb[name], header_row

    for name in wb.sheetnames:
        ws = wb[name]
        title = str(ws.cell(row=1, column=1).value or "").strip().lower()
        if INDICATOR_SHEET_TITLE_MARKER in title:
            header_row = _find_header_row(ws)
            if header_row is not None:
                year_match = _YEAR_IN_TITLE_RE.search(title)
                year = year_match.group(1) if year_match else name
                return year, ws, header_row

    raise ValueError(
        "No sheet in the Indicator workbook has the expected 'District' / "
        "'Total Population' header layout -- check the sheet structure or update "
        "src/pipeline/indicator_sheet_vpd.py's COLUMNS mapping."
    )


def load_indicator_sheet(path: Path) -> dict:
    """Returns {'year': ..., 'districts': [...], 'provincial_total': {...}}
    -- every row read positionally per COLUMNS, no formula recomputation
    (the sheet's own values, including its own 'Provincial Total' row, are
    trusted as-is, same 'trust the sheet' rule as Coverage's UC-level
    Access/Utilisation)."""
    wb = openpyxl.load_workbook(path, data_only=True)
    year, ws, header_row = _select_year_sheet(wb)
    # Historically: header row 2, one sub-header row (3), data from row 4 --
    # i.e. data starts 2 rows below the header. Computed from the detected
    # header row rather than a fixed row number, so a newer export's extra
    # blank row shifts everything down together, not just the header.
    data_start_row = header_row + 2

    def _row(r):
        return {key: ws.cell(row=r, column=col).value for key, col in COLUMNS.items()}

    districts = []
    provincial_total = None
    r = data_start_row
    while True:
        district_name = ws.cell(row=r, column=COLUMNS["district"]).value
        if district_name is None:
            break
        row = _row(r)
        if str(district_name).strip().lower() in PROVINCIAL_TOTAL_LABELS:
            provincial_total = row
            break
        districts.append(row)
        r += 1

    if provincial_total is None:
        raise ValueError(
            f"No provincial-total row (labelled 'Provincial Total' or 'Provincial') found "
            f"below the district rows in the '{year}' sheet -- the workbook layout may have changed."
        )
    return {"year": year, "districts": districts, "provincial_total": provincial_total}


def build_key_indicators_summary(sheet: dict) -> dict:
    """One row per highlighted key indicator: the Provincial Total's own
    value (trusted as-is), plus the highest/lowest-value district for that
    indicator among the real per-district rows -- both genuinely sourced
    from the workbook, not a fabricated 'target'. No numeric target exists
    anywhere in this workbook (confirmed by inspection), so none is
    invented here; the dashboard shows that fact explicitly rather than a
    guessed WHO benchmark."""
    districts = sheet["districts"]
    prov = sheet["provincial_total"]
    rows = []
    for spec in KEY_INDICATORS:
        key = spec["key"]
        valued = [(d["district"], d[key]) for d in districts if isinstance(d[key], (int, float))]
        highest = max(valued, key=lambda t: t[1]) if valued else None
        lowest = min(valued, key=lambda t: t[1]) if valued else None
        rows.append({
            "key": key, "label": spec["label"], "unit": spec["unit"],
            "provincial_value": prov[key],
            "highest_district": {"district": highest[0], "value": highest[1]} if highest else None,
            "lowest_district": {"district": lowest[0], "value": lowest[1]} if lowest else None,
        })
    return {
        "status": "ok",
        "year": sheet["year"],
        "districts_covered": len(districts),
        "total_population": prov["total_population"],
        "total_cases_reported": prov["total_cases_reported"],
        "indicators": rows,
        "measles_incidence_map": build_measles_incidence_map(sheet),
        "district_table": build_district_table(sheet),
    }


def build_district_table(sheet: dict) -> list[dict]:
    """Per-district case counts from the Indicator Sheet's own columns,
    shaped to replace the MSL line list's district-wise suspected/confirmed
    table on the dashboard (a separate, independent source -- see this
    module's docstring -- so the two are never mixed in one row). Uses the
    sheet's own already-aggregated 'measles_total' (lab confirmed + double
    infection + epi-linked + clinically compatible, all trusted as-is, same
    'trust the sheet' rule as everywhere else in this module) rather than
    recomputing a sum, and its own 'rubella_confirmed_cases'."""
    rows = []
    for row in sheet["districts"]:
        rows.append({
            "district": row["district"],
            "total_cases_reported": row["total_cases_reported"],
            "measles_lab_confirmed": row["measles_lab_confirmed"],
            "measles_total": row["measles_total"],
            "rubella_confirmed_cases": row["rubella_confirmed_cases"],
        })
    return rows


def build_measles_incidence_map(sheet: dict) -> dict:
    """Per-district measles incidence (cases per million, this sheet's own
    annualized figure -- never derived from a population proxy elsewhere in
    this project, see CLAUDE.md's "Confirmed VPD decisions") banded into the
    WHO-standard Low/Moderate/Disruptive-outbreak categories, keyed by this
    project's canonical district name so it shares kp_districts.geojson with
    every other choropleth map."""
    canonical_values = set(DISTRICT_NAME_CANONICAL.values())
    features = {}
    unmapped = []
    for row in sheet["districts"]:
        raw_name = str(row["district"]).strip()
        # A newer export (2026-10) already spells several districts this
        # project's canonical way directly (e.g. "Bajaur", "Tor Ghar") rather
        # than the older misspelling DISTRICT_NAME_CANONICAL's keys were
        # built from -- fall back to treating an already-canonical spelling
        # as itself, rather than only ever matching a known raw variant.
        canonical = DISTRICT_NAME_CANONICAL.get(raw_name) or (raw_name if raw_name in canonical_values else None)
        if canonical is None:
            unmapped.append(raw_name)
            continue
        value = row["measles_incidence_per_million"]
        value = value if isinstance(value, (int, float)) else None
        band = _incidence_band(value)
        features[canonical] = {
            "measles_incidence_per_million": value,
            "category": band["color"] if band else None,
            "category_label": band["label"] if band else None,
        }
    return {"unmapped_districts": sorted(unmapped), "features": features}


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def run_indicator_sheet(raw_dir: Path | None = None, processed_dir: Path | None = None) -> dict | None:
    """Independent of the MSL line list pipeline (run_vpd.py) -- an
    Indicator Sheet upload with no line list present still produces
    data/processed/vpd_indicator_summary.json, and vice versa. Returns None
    (writes nothing) if no Indicator Sheet workbook is found."""
    raw_dir = raw_dir or (PROJECT_ROOT / "data" / "raw")
    processed_dir = processed_dir or PROCESSED_DIR
    files = find_indicator_sheet_files(raw_dir)
    if not files:
        return None

    print("\nMeasles Indicator Sheet pipeline starting...")
    path = files[0]
    print(f"  Loading {path.name}...")
    try:
        sheet = load_indicator_sheet(path)
    except ValueError as e:
        # Preserve the real, specific message (e.g. a missing header/
        # provincial-total row) as SystemExit so the web app shows it
        # directly to the user instead of a generic "something unexpected
        # went wrong" -- same convention as run.py/run_vpd.py's load-failure
        # handling, which this module had never been given.
        raise SystemExit(f"\nFAILED loading {path.name}: {e}") from e
    summary = build_key_indicators_summary(sheet)
    print(f"    {sheet['year']} sheet: {summary['districts_covered']} districts, "
          f"{summary['total_cases_reported']} total cases reported")

    processed_dir.mkdir(parents=True, exist_ok=True)
    with open(processed_dir / "vpd_indicator_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print("Measles Indicator Sheet pipeline finished OK.")
    return summary
