# EPI Dashboard & Bulletin System — Project Memory

## Status

- **Part 1a (coverage pipeline)**: done. `src/pipeline/{load,clean,indicators,run}.py`.
- **Part 1b (VPD surveillance pipeline)**: done for measles-rubella, diphtheria,
  pertussis, NNT. `src/pipeline/{load_vpd,clean_vpd,indicators_vpd,run_vpd}.py`.
  AFP is stubbed (`AFP_STUB` in run_vpd.py) — no AFP line list has been received.
  Supervisory-visit domain (Part 1c) not started — no file received yet.
- **Part 2 (dashboard)**: done. `src/dashboard/{build.py,template.html}` ->
  `output/dashboard.html`, single self-contained file, Chart.js inlined
  (`src/dashboard/chart.umd.min.js`, downloaded once, not CDN-loaded).
- **Part 3 (bulletin)**: done for VPD surveillance (PDF + Excel annex + PPTX).
  `src/bulletin/{build.py,exports.py,template.html}` ->
  `output/Bulletin_Week_<N>_<year>.{pdf,xlsx,pptx}`. Rendered with Playwright
  (Chromium), one A4 page, matches the user-supplied sample bulletin layout.
  Word export not built (brief: only build on request, warn layout won't survive).
- 46 tests passing (`pytest tests/`), pinned to real numbers throughout.
- Run everything with `python run_weekly.py` from the project root.

## Confirmed bulletin decisions

- **Bulletin week selection**: `run_vpd.build_bulletin_section()` defaults to
  the latest epi_week present in the VPD file. "This week" = exactly that
  epi_week; "cumulative" = every row with epi_week <= that week (so a Week 30
  bulletin run from a file containing weeks 1-32 would NOT include weeks
  31-32). No CLI flag to pick an older week yet — not needed until there's a
  reason to regenerate a past week's bulletin.
- **Incidence-rate rows are shown, not hidden**: the sample bulletin has
  "Measles incidence rate per million" etc. as real numbers; ours shows
  `N/A*` with a footnote explaining why (no population denominator — see
  "Confirmed VPD decisions" above), rather than deleting the row. Matches the
  layout, doesn't fabricate the number.
- **"Eligible" suspected cases** (for the zero-dose-% headline stat and the
  two vaccination-status icon panels) = age >= 9 months (`is_eligible_age` in
  clean_vpd.py) — MCV1 is given at 9 months, so younger cases aren't a
  meaningful vaccination-status denominator. Cases under 9m, or with an
  invalid age, are excluded from these panels only — they're still counted in
  every other bulletin figure (suspected total, classification breakdown, etc).
- **"Confirmed cases" vaccination-status panel** combines measles-confirmed
  OR rubella-confirmed (`is_confirmed` in clean_vpd.py) into one denominator,
  matching the sample's single "confirmed cases" panel rather than splitting
  by disease.
- **Diphtheria age bands** are 5-year bands (`<1y`, `1-5`, `6-10`, ...)
  computed dynamically from whatever ages are in the data — not padded or
  capped to match the sample's exact band list, since the sample's range was
  just whatever happened to be in their Week 30 cutoff, not a fixed schema.
- **Key messages are a genuinely editable input**: `data/bulletin_inputs/key_messages.json`,
  loaded fresh by the pipeline every run, not hardcoded or auto-generated.
  Ships with the same 4 messages as the reference sample (generic
  epidemiological boilerplate, not specific fabricated claims) — edit that
  file by hand before each week's run.
- **One auto-generated comparison sentence implemented**: MSL and diphtheria
  week-over-week case-count deltas (`indicators_vpd.week_over_week_delta`),
  shown in the highlights bullets. Did NOT implement the brief's other
  example ("N UCs moved into Category 4") — that needs a weekly (not just
  two-snapshot) coverage history, which doesn't exist yet.

Data system for the Expanded Programme on Immunization (EPI), Directorate General
Health Services, Khyber Pakhtunkhwa. Pipeline → Dashboard + Bulletin. The bulletin
NEVER recomputes an indicator — it reads only what `src/pipeline` produced, so the
dashboard and bulletin are mathematically incapable of disagreeing.

## Data received so far

| File | Sheets | Period | Notes |
|---|---|---|---|
| `data/raw/Dec 2025 Coverage Analysis (0-11).xlsx` | District, Teshil, UC Wise Analysis - Coverages, UC Wise Analysis - Difference i | **Monthly**, December 2025 | `(0-11)` in the filename = age band (surviving infants 0–11 months), NOT calendar months. Confirmed this is the file the original build brief's data-quality numbers (925 consistency fails, 56 zero-target UCs, BCG 1203%, Tor Ghar target 95,554) were taken from — exact match. |
| `data/raw/Jan to Dec 2025.xlsx` | same 4 sheets | **Cumulative**, Jan–Dec 2025 | Same 37 district rows, same structure, larger (annual) numbers. Gives us a real second time point instead of a stub. |

VPD surveillance and supervisory-visit files have **not** been provided yet. Domains 2
and 3 are built against a documented, versioned schema (`src/pipeline/schemas.py`,
once added) with stub data, so the dashboard/bulletin layout can be demoed. A schema
change there should be a config edit, not a rewrite.

## Confirmed sheet structure (identical in both files)

- **`District ` sheet** (trailing space in the actual sheet name): 1 header row + 37
  district rows (36 real districts + 1 mislabeled "Tor Ghar" row). Raw counts AND
  targets present for BCG, Penta I/II/III, IPV I/II, MR I, TCV, FIC, plus Dropout,
  Access, Utilisation, District Category, and Category-1..4 counts. Rows past row 38
  are fully blank (Excel export padding) — bounded by last-non-null-row per sheet,
  not `max_row`.
- **`Teshil ` sheet** (trailing space): same indicator set as District, at tehsil
  level, plus a second unrelated block of columns starting around column AI
  (District, Total Tehsils, Category-1..4, `Check`) — a per-district tehsil-category
  rollup. Meaning of `Check` column (values seen: 0, -1, -2, -3) is **not yet
  confirmed** — looks like a QC delta between summed Category counts and Total
  Tehsils, but this is a guess. Ask before using it in any output.
- **`UC Wise Analysis - Coverages` sheet**: 1,376 UC rows. **Percentages only** — BCG,
  OPV0-3, Penta I-III, PCV I-III, IPV I-II, Rota I-II, MR I, FIC, TCV, Dropout
  (P1-P3), Access, Utilisation, Category. **No raw numerator/denominator or target at
  UC level anywhere in the file.**
- **`UC Wise Analysis - Difference i` sheet**: same-visit consistency checks
  (BCG-OPV0, P1-OPV1, P1-PCV1, P1-R1, P2-OPV2, P2-PCV2, P2-R2, P3-OPV3, P3-PCV3,
  P3-IPV1, MR1-TCV). `Unique Identifier` column is a broken
  `QUERY('Raw Data'!A:BO, ...)` formula — the `Raw Data` tab does not exist in either
  file, so it's null for nearly every row. Do not attempt to resolve it; it's not
  needed (UC Code is the real join key and is complete).

## Confirmed decisions

- **UC-level Access/Utilisation/Category/Dropout/% are treated as authoritative and
  passed through as-is, never recomputed.** (User: "trust the sheet.") Reason: the
  UC sheet has no raw counts or targets, so the exact Access/Utilisation cutoff
  formula can't be independently derived or verified — re-deriving it would mean
  guessing, and this is public-health data. `indicators.py` functions for
  Access/Utilisation/Category are pass-through/validation functions, not
  calculations, and their docstrings say so explicitly.
- **District/Tehsil level**: raw counts and targets ARE present, so the pipeline
  independently computes coverage % (`count / target * 100`) for cross-check against
  the sheet's own %, and computes dropout as `(Penta1# − Penta3#) / Penta1# × 100`
  for the same reason. Any mismatch between our computed % and the sheet's % beyond
  rounding gets logged in the data-quality report, not silently accepted.
  Access/Utilisation/Category at District/Tehsil level are passed through, same
  reasoning as UC level.
- **Province/district aggregates are always computed from summed raw counts/targets
  (District sheet), never by averaging UC or Tehsil percentages.** This is what
  structurally satisfies "flag outliers, don't let them distort aggregates" — UC-level
  outlier %s never enter a district/province average in the first place.
- **Tor Ghar row** in the District sheet = Khyber Pakhtunkhwa province total,
  mislabeled. Pipeline renames it to `KP Province Total`, tags
  `is_province_total=True`, and excludes it from district rankings/comparisons by
  default. Real Tor Ghar district data is simply missing from these files.
- **Negative dropout is common, not rare**: 316/1,376 UCs in the December file,
  161/1,376 in the annual file. Flagged (`is_negative_dropout`), value kept as-is
  (not zeroed or dropped) — it's a real Excel artifact (Penta3 > Penta1 at that UC),
  not something safe to "fix" without knowing which count is wrong.
- **Outlier threshold**: UC-level antigen % > 120% is flagged `is_outlier`. Value is
  kept and flagged, never dropped or clipped — downstream displays should visually
  distinguish flagged cells rather than hide them.
- **Zero-target UCs** (`#DIV/0!` in Utilisation/Category — 56 in Dec, 11 in annual):
  value becomes `null` (not 0, not dropped), `is_zero_target=True`, row stays in the
  dataset so the UC still shows up in tables with an explicit "no target set" state.
- **Junk Tehsil rows** (Mastuj, Molkhow, Torkhow — all Chitral, district field is
  literal string `\N`, target 0, `#DIV/0!` throughout): dropped from the Tehsil
  table, logged by name and reason in the data-quality report.
- **District/Tehsil/UC name spelling is fully consistent** across all 4 sheets in
  both files received so far — no variants found. Normalization code still handles
  case/whitespace defensively since the brief warned this may not hold for future
  months' files.
- **UC codes**: 1,376 unique, no duplicates, in both files. December file's
  Difference sheet has 10 UC codes not present in Coverages (out of 1,387 rows there
  vs 1,376 real UCs) — logged as a minor join-mismatch flag, not blocking.

## VPD surveillance data (received)

`data/raw/KP VPDs Line List Week 1-32,2026.xlsx` — 5 sheets, all **case-level line
lists** (one row per case), header on row 2 (row 1 is a merged title), data from row
3. Covers epi weeks 1-32 of 2026 (rash/onset dates span 2025-12-31 to 2026-08-15) —
a completely different period axis from the coverage files (weekly cumulative-to-date,
not monthly). Treated as its own domain/table, not joined to coverage periods.

| Sheet | Rows | Disease | Key fields confirmed |
|---|---|---|---|
| `MSL LINE-LIST` | 10,336 | Measles-Rubella | Final classification (9 distinct values + a case-casing duplicate — see below), Lab Result Measles/Rubella, Total msl vaccine doses received (0/1/2/`"unknown"` literal string), Age in Month, Sex, District/Tehsil/UC, Quantity Adequate (sample adequacy), Outcome, Complications |
| `DIPHTHERIA LINE-LIST ` | 167 | Diphtheria | Final classification (Discarded/Lab Confirmed/Pending/null), Lab Result, doses received, Outcome (incl. 1 Death), Age in Month |
| `NNT_LineList` | 132 | Neonatal tetanus | Age in **days** (not months — NNT is neonates <28 days), Outcomes (incl. Died/Death — two different literal strings used), TT doses to mother |
| `Pertusis line-list` | 45 | Pertussis | Same shape as Diphtheria; header has a 2-row merged sub-header at columns 25-26 (`Quantity Adequate`/`Cold Chain OK` nested under `Condition of Specimen`) |
| `AEFI_LineLists_Report` | 1 | Adverse Events Following Immunization | **Not in the original brief's indicator list at all.** Only 1 real record. Not building against this yet — flagged for a decision. |

Confirmed data-quality issues in this file (same "flag loudly, never drop silently"
policy as domain 1):
- **MSL `Final classification` has a casing duplicate**: `'Laboratory Confirmed
  Measles'` (3,795 rows) vs `'laboratory Confirmed Measles'` (35 rows, lowercase
  'l') — same category, must be normalized case-insensitively before counting, or
  the bulletin's classification table under-counts confirmed measles by 35.
- **MSL `Age in Month` has data-entry garbage**: range seen is -935 to 916 months.
  65 of 10,336 rows (0.6%) fall outside a sane 0-180 month range; most of those 65
  are large-but-plausible adult ages (180-480 months, i.e. adult contacts under
  outbreak investigation — legitimate for measles-rubella surveillance), a much
  smaller number are impossible negative values. Needs a defined cutoff and
  explicit flag, not a silent drop — open question below.
- **Diphtheria doses-received has a literal `111`** for one row (max plausible is
  low single digits) and mixes `int` 0/1/2 with the literal string `"unknown"` —
  same pattern as MSL's dose field.
- District names in this file match the coverage files' 37-name list exactly
  (checked against MSL's 37 distinct districts). Diphtheria/NNT/Pertussis only have
  cases in a subset of districts, which is expected (not every district has every
  disease every week) — not a data problem, just fewer rows.

## Confirmed VPD decisions

- **AFP**: no AFP line list exists in the VPD file received. Dashboard/bulletin AFP
  sections are stubbed with an explicit "awaiting data" state, not fabricated
  numbers. Swap in real data later without a rebuild once an AFP line list arrives.
- **Incidence-rate indicators are out of scope for now** (measles/rubella per
  million, NMR rate per 100,000) — no population denominator exists in either file
  received. Not approximated using the vaccination target as a population proxy.
  Revisit if/when a population source is provided.
- **MSL `Age in Month` validity**: negative ages are always a data error
  (excluded from age-bucket denominators, case stays in every other count). No
  upper bound — ages above 180 months are kept and fall into the `60m+` bucket
  as-is (adult contacts are a legitimate part of measles-rubella surveillance).

## Open questions (not yet answered — do not guess)

- Exact meaning/formula of the Tehsil sheet's `Check` column.
- Whether "flag outliers, don't distort aggregates" should also suppress an
  outlier UC's Category from UC-category breakdown counts on the dashboard, or just
  visually flag it while still counting it.
- Supervisory-visit file schema — not received yet (user: "can be added later").
- Whether "Laboratory Confirmed Measles and Rubella" (132 MSL rows) should be
  folded into the "Double Infection" category (46 rows) or kept as its own
  category — currently kept separate and reported as-is; brief's 6-category list
  (lab confirmed / discarded / clinically compatible / double infection / epi
  confirmed / pending) doesn't have a slot for it.
- Whether the AEFI sheet (1 real record) should be built into the system at all —
  not requested in the original brief.
