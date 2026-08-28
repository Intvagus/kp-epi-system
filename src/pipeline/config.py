"""Run-level configuration: thresholds, period metadata, column maps.

Adding a new monthly file that this repo hasn't seen before should only ever
require a new entry in PERIOD_OVERRIDES (or, if the filename matches the
pattern already, nothing at all) -- never a code change.
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Period:
    period_id: str
    period_type: str  # "monthly" | "cumulative_annual"
    label: str


# Exact-filename overrides. Used when the filename doesn't parse cleanly, or
# to pin down a period that the regex heuristics below would get wrong.
PERIOD_OVERRIDES = {
    "Dec 2025 Coverage Analysis (0-11).xlsx": Period("2025-12", "monthly", "December 2025"),
    "Jan to Dec 2025.xlsx": Period("2025-annual", "cumulative_annual", "Jan-Dec 2025 (cumulative)"),
}

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_YEAR_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{4})\b", re.I
)
_JAN_TO_DEC_RE = re.compile(r"jan\s+to\s+dec\s+(\d{4})", re.I)


def infer_period(filename: str) -> Period:
    """Infer a Period from a raw filename. Raises with a clear message if it can't.

    Recognises "<Month> <Year>..." -> monthly, and "Jan to Dec <Year>" -> cumulative_annual.
    Anything else must be added to PERIOD_OVERRIDES by hand.
    """
    if filename in PERIOD_OVERRIDES:
        return PERIOD_OVERRIDES[filename]

    m = _JAN_TO_DEC_RE.search(filename)
    if m:
        year = m.group(1)
        return Period(f"{year}-annual", "cumulative_annual", f"Jan-Dec {year} (cumulative)")

    m = _MONTH_YEAR_RE.search(filename)
    if m:
        mon, year = m.group(1).lower(), m.group(2)
        return Period(f"{year}-{_MONTHS[mon]:02d}", "monthly", f"{mon.title()} {year}")

    raise ValueError(
        f"Cannot infer reporting period from filename {filename!r}. "
        f"Add an entry to PERIOD_OVERRIDES in src/pipeline/config.py, e.g.:\n"
        f'  "{filename}": Period("2026-01", "monthly", "January 2026"),'
    )


# Thresholds — configurable, not hardcoded in dashboard/bulletin templates.
COVERAGE_GOOD = 80       # >= this = good (green)
COVERAGE_WARNING = 60    # >= this, < COVERAGE_GOOD = warning (amber); below = poor (red)
DROPOUT_GOOD = 10        # <= this = good
DROPOUT_WARNING = 20     # <= this, > DROPOUT_GOOD = warning; above = poor
OUTLIER_PCT_THRESHOLD = 120  # UC-level antigen % above this is flagged as an outlier

SHEET_NAMES = {
    "district": "District ",
    "tehsil": "Teshil ",
    "uc_coverages": "UC Wise Analysis - Coverages",
    "uc_difference": "UC Wise Analysis - Difference i",
}

PROVINCE_TOTAL_DISTRICT_LABEL = "Tor Ghar"  # mislabeled row in the District sheet
PROVINCE_TOTAL_NAME = "KP Province Total"

JUNK_TEHSIL_DISTRICT_MARKERS = {None, "\\N"}

# Maps this project's 36 real Coverage-file district names (KP Province Total
# excluded -- it's a province-wide aggregate row, not a district) to the
# boundary polygon name in dashboard/kp_districts.geojson (District/ADM2
# boundaries for Pakistan, sourced from geoBoundaries --
# https://www.geoboundaries.org, CC-BY 4.0). Several of our districts are
# newer administrative sub-splits (Chitral, Kohistan, Kurram, and South
# Waziristan were each divided into 2-3 districts more recently than this
# boundary set) that don't have their own separate polygon yet -- these are
# combined onto their shared parent polygon by the map-builder, with the
# mapped figure computed by SUMMING raw counts across the sub-districts,
# never by averaging percentages -- see indicators.py's module docstring.
# Verified exhaustive for the Coverage domain: every one of the 36 real
# district names has an entry here, and every boundary name on the right
# exists in kp_districts.geojson (see tests/test_coverage_summary.py).
# Shared with the Monitoring domain's district maps (run_monitoring.py) --
# a Monitoring district name that isn't spelled the same way here falls out
# as "unmapped" (flagged, not guessed at), same as any other domain.
DISTRICT_TO_BOUNDARY = {
    "Abbottabad": "Abbottabad", "Bajaur": "Bajaur", "Bannu": "Bannu", "Battagram": "Battagram",
    "Buner": "Buner", "Charsadda": "Charsadda", "Chitral Lower": "Chitral", "Chitral Upper": "Chitral",
    "D.I. Khan": "Dera Ismail Khan", "Dir Lower": "Lower Dir", "Dir Upper": "Upper Dir",
    "Hangu": "Hangu", "Haripur": "Haripur", "Karak": "Karak", "Khyber": "Khyber", "Kohat": "Kohat",
    "Kohistan Lower": "Kohistan", "Kohistan Upper": "Kohistan", "Kolai Palas Kohistan": "Kohistan",
    "Kurram Lower and Central": "Kurram", "Kurram Upper": "Kurram", "Lakki Marwat": "Lakki Marwat",
    "Malakand": "Malakand", "Mansehra": "Mansehra", "Mardan": "Mardan", "Mohmand": "Mohmand",
    "North Waziristan": "North Waziristan", "Nowshera": "Nowshera", "Orakzai": "Orakzai",
    "Peshawar": "Peshawar", "SW Mehsud Belt": "South Waziristan", "SW Wazir Belt": "South Waziristan",
    "Shangla": "Shangla", "Swabi": "Swabi", "Swat": "Swat", "Tank": "Tank",
}

# --- VPD surveillance (domain 2) ---
# Case-level line lists, one workbook per reporting run (filename carries the week
# range, e.g. "KP VPDs Line List Week 1-32,2026.xlsx"). Confirmed with the user:
# age validity has no upper bound (adult contacts are legitimate for
# measles-rubella surveillance) -- only a negative age is a data error.
VPD_SHEET_NAMES = {
    "msl": "MSL LINE-LIST",                  # measles-rubella
    "diphtheria": "DIPHTHERIA LINE-LIST ",   # trailing space is real, matches the workbook
    "nnt": "NNT_LineList",
    "pertussis": "Pertusis line-list",
}
VPD_HEADER_ROW = 2  # 1-indexed; row 1 is a merged title, data starts row 3

AGE_BUCKETS_MONTHS = [
    (0, 8, "0-8m"),      # not yet due for MCV1
    (9, 23, "9-23m"),
    (24, 59, "24-59m"),
    (60, None, "60m+"),  # no upper bound -- confirmed with user
]

# Case-insensitive canonicalisation of MSL 'Final classification' free text --
# the source file has a confirmed casing duplicate ('Laboratory Confirmed
# Measles' vs 'laboratory Confirmed Measles', 3795 vs 35 rows) that must not be
# counted as two categories.
MSL_CLASSIFICATION_CANONICAL = {
    "discarded": "Discarded",
    "laboratory confirmed measles": "Laboratory Confirmed Measles",
    "clinically compatible measles": "Clinically Compatible Measles",
    "pending classification": "Pending Classification",
    "laboratory confirmed measles and rubella": "Laboratory Confirmed Measles and Rubella",
    "double infection": "Double Infection",
    "epidemiologically confirmed measles": "Epidemiologically Confirmed Measles",
    "clinically compatible rubella": "Clinically Compatible Rubella",
    "epidemiologically confirmed rubella": "Epidemiologically Confirmed Rubella",
}

DOSE_STATUS_LABELS = {0: "Zero dose", 1: "1 dose", 2: "2 doses"}
DOSE_STATUS_UNKNOWN = "Unknown"
DOSE_STATUS_MAX_PLAUSIBLE = 4  # a value above this (e.g. the '111' seen in the Diphtheria sheet) is a data error, not a real dose count

_VPD_WEEK_RANGE_RE = re.compile(r"week\s+(\d+)\s*-\s*(\d+)\s*,\s*(\d{4})", re.I)


# --- Monitoring / supervisory visits (domain 3) ---
# Two independent report exports from the field-monitoring system, both saved
# as HTML tables with a ".xls" extension (not real Excel binary/OOXML --
# confirmed via `file`), so they're read with pandas.read_html, not
# openpyxl. Filenames carry no reliable period ("RCA_Report_2.xls",
# "Supervisory_Checklist_Report.xls") -- the reporting window is read from
# the data itself (min/max visit date), not inferred from the filename.
RCA_VACCINE_ANTIGENS = [
    "BCG", "HepB", "OPV 0", "OPV 1", "OPV 2", "OPV 3", "Rota 1", "Rota 2",
    "Penta 1", "Penta 2", "Penta 3", "PCV 1", "PCV 2", "PCV 3",
    "IPV I", "IPV II", "TCV", "MR I", "MR II",
]

RCA_STATUS_CANONICAL = {
    "yesvaccinat": "Vaccinated",
    "notvaccinat": "Not Vaccinated",
    "notapp": "Not Applicable",
    "notapplicable": "Not Applicable",
}


def infer_vpd_period(filename: str) -> Period:
    """VPD line lists are cumulative-to-date over a week range, e.g.
    'KP VPDs Line List Week 1-32,2026.xlsx' -- a different period model from
    the monthly/annual coverage files (see Period.period_type
    'cumulative_weekly'). Add a new pattern here, not a hardcoded filename, if
    a future export names the range differently."""
    m = _VPD_WEEK_RANGE_RE.search(filename)
    if m:
        start_week, end_week, year = m.groups()
        return Period(f"{year}-W{start_week}-{end_week}", "cumulative_weekly",
                       f"Weeks {start_week}-{end_week}, {year}")
    raise ValueError(
        f"Cannot infer VPD reporting week range from filename {filename!r}. "
        f"Expected a 'Week <start>-<end>,<year>' pattern in the filename."
    )
