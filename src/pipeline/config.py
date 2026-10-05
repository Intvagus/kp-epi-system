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
# "Jan to Dec <year>" was the only cumulative pattern originally seen (a full
# completed year) -- generalized to "Jan to <any month> <year>" after a real
# "Jan to Aug 2026.xlsx" upload showed the same source system also exports
# year-to-date cumulative files partway through the year, not just full
# years. The Dec case keeps its exact original period_id/label ("<year>-annual"
# / "Jan-Dec <year> (cumulative)", pinned by existing tests); any other end
# month gets its own distinct period_id so a same-year partial- and full-year
# cumulative file could never collide.
_JAN_TO_MONTH_RE = re.compile(
    r"jan\s+to\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{4})", re.I
)


def infer_period(filename: str) -> Period:
    """Infer a Period from a raw filename. Raises with a clear message if it can't.

    Recognises "<Month> <Year>..." -> monthly, and "Jan to <Month> <Year>" ->
    cumulative (year-to-date through that month; "Jan to Dec" = full year).
    Anything else must be added to PERIOD_OVERRIDES by hand.
    """
    if filename in PERIOD_OVERRIDES:
        return PERIOD_OVERRIDES[filename]

    m = _JAN_TO_MONTH_RE.search(filename)
    if m:
        end_month, year = m.group(1).lower(), m.group(2)
        if end_month == "dec":
            return Period(f"{year}-annual", "cumulative_annual", f"Jan-Dec {year} (cumulative)")
        return Period(
            f"{year}-cum-{_MONTHS[end_month]:02d}", "cumulative_annual",
            f"Jan-{end_month.title()} {year} (cumulative)",
        )

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

# A newer source export lays the District and Teshil sheets' data out as two
# side-by-side blocks (plus a third, unused Category-rollup block) inside one
# sheet instead of two separate sheets -- confirmed by direct inspection of a
# real "Jan to Aug 2026" upload (2026-09). `load.py::_load_combined_district_tehsil`
# splits this sheet back into the same district/tehsil shape the rest of the
# pipeline already expects; `detect.py` accepts either layout as a valid
# Coverage workbook.
COMBINED_DISTRICT_TEHSIL_SHEET = "Dist & Teshil Summary"

PROVINCE_TOTAL_DISTRICT_LABEL = "Tor Ghar"  # legacy mislabeled row in the District sheet
PROVINCE_TOTAL_JUNK_LABEL = "\\N"  # some newer exports put the real total under this literal marker instead
PROVINCE_TOTAL_NAME = "KP Province Total"

# A District-sheet row carrying one of the two labels above is only treated as
# the real province-wide total if its own target is at least this fraction of
# the summed target of every OTHER district row -- a genuine province total is
# roughly equal to that sum, while a real single small district is a tiny
# fraction of it. Needed from 2026-10: a newer export started shipping real
# "Tor Ghar" district data (a real KP district) under the exact label this
# pipeline used to always treat, unconditionally, as the mislabeled province
# total -- which silently swallowed the real district (excluded from every
# district table/ranking/map) and replaced every province-wide KPI with that
# tiny single district's own numbers. See CLAUDE.md.
PROVINCE_TOTAL_MIN_SHARE_OF_OTHERS = 0.5

JUNK_TEHSIL_DISTRICT_MARKERS = {None, "\\N"}

# Maps this project's 36 real Coverage-file district names (KP Province Total
# excluded -- it's a province-wide aggregate row, not a district) to the
# boundary polygon name in dashboard/kp_districts.geojson.
#
# As of this map's replacement, this is an IDENTITY mapping: every district,
# including every newer sub-split (Chitral, Kohistan, Kurram, South
# Waziristan), has its own real, separate boundary polygon -- extracted from
# the user-provided reference map (KP_MAP_1.pptx, a labeled district-level
# vector map; geometry traced from its own vector shapes, bezier curves
# flattened and Douglas-Peucker-simplified for embedding size, district
# names confirmed by direct visual inspection against the pipeline's own
# district-name spelling). The dict is kept (rather than dropped for a plain
# set) because build_district_map()/rca_district_map()/
# supervisory_district_map() all key off it generically, and because it's
# still the single place that would need a real combining entry if a future
# boundary set ever lacked one of these polygons again.
#
# One assumption flagged, not guessed at silently: SW Wazir Belt / SW Mehsud
# Belt (South Waziristan's tribal-belt-based split) are matched to the
# reference map's "Wazir Belt (Upper)" / "Mehsud Belt (Lower)" shapes by
# adjacency -- Wazir Belt borders North Waziristan directly in the source
# map, consistent with it being the northern sub-division; Mehsud Belt does
# not. The reference map has no per-shape name embedded to confirm this
# directly (see extraction notes) -- flagged here in case a more direct
# source of the belt boundary emerges.
#
# Verified exhaustive for the Coverage domain: every one of the 36 real
# district names has an entry here, and every boundary name on the right
# exists in kp_districts.geojson (see tests/test_coverage_summary.py).
# Shared with the Monitoring domain's district maps (run_monitoring.py) --
# a Monitoring district name that isn't spelled the same way here falls out
# as "unmapped" (flagged, not guessed at), same as any other domain.
DISTRICT_TO_BOUNDARY = {
    "Abbottabad": "Abbottabad", "Bajaur": "Bajaur", "Bannu": "Bannu", "Battagram": "Battagram",
    "Buner": "Buner", "Charsadda": "Charsadda", "Chitral Lower": "Chitral Lower", "Chitral Upper": "Chitral Upper",
    "D.I. Khan": "D.I. Khan", "Dir Lower": "Dir Lower", "Dir Upper": "Dir Upper",
    "Hangu": "Hangu", "Haripur": "Haripur", "Karak": "Karak", "Khyber": "Khyber", "Kohat": "Kohat",
    "Kohistan Lower": "Kohistan Lower", "Kohistan Upper": "Kohistan Upper", "Kolai Palas Kohistan": "Kolai Palas Kohistan",
    "Kurram Lower and Central": "Kurram Lower and Central", "Kurram Upper": "Kurram Upper", "Lakki Marwat": "Lakki Marwat",
    "Malakand": "Malakand", "Mansehra": "Mansehra", "Mardan": "Mardan", "Mohmand": "Mohmand",
    "North Waziristan": "North Waziristan", "Nowshera": "Nowshera", "Orakzai": "Orakzai",
    "Peshawar": "Peshawar", "SW Mehsud Belt": "SW Mehsud Belt", "SW Wazir Belt": "SW Wazir Belt",
    "Shangla": "Shangla", "Swabi": "Swabi", "Swat": "Swat", "Tank": "Tank",
    # "Tor Ghar" has a real boundary polygon in kp_districts.geojson (see
    # CLAUDE.md -- 37 features total, this is the 37th) but was never added
    # here, since every Coverage file received until 2026-10 mislabeled its
    # province-total row "Tor Ghar" rather than shipping real data for it
    # (clean.py's magnitude check now tells the two apart -- see
    # PROVINCE_TOTAL_MIN_SHARE_OF_OTHERS). Without this entry, a file with
    # real Tor Ghar data made build_district_map() report it as unmapped,
    # which made every antigen-wise district map on the dashboard silently
    # disappear entirely (template.html's antigenMapsGridHtml bails out on
    # any unmapped district) -- found from a real user-uploaded file.
    "Tor Ghar": "Tor Ghar",
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
