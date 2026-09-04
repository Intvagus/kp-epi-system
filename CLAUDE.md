# EPI Dashboard & Bulletin System — Project Memory

## Status

- **Part 1a (coverage pipeline)**: done. `src/pipeline/{load,clean,indicators,run}.py`.
- **Part 1b (VPD surveillance pipeline)**: done for measles-rubella, diphtheria,
  pertussis, NNT. `src/pipeline/{load_vpd,clean_vpd,indicators_vpd,run_vpd}.py`.
  AFP is stubbed (`AFP_STUB` in run_vpd.py) — no AFP line list has been received.
  A separate, independent source (`src/pipeline/indicator_sheet_vpd.py`) reads
  the "Measles Indicator Sheet" workbook — one sheet per year (e.g. `2026`),
  a per-district table of pre-aggregated surveillance performance
  indicators plus the source's own "Provincial Total" row, entirely
  distinct from the MSL line list (different district total, since it's a
  different pull from the source system — the two are shown side by side on
  the dashboard, never reconciled against each other). Detected by an A1
  cell title marker (`"...Indicator Sheet-<year>"`), not sheet names, since
  every sheet is named after its year. 6 of its ~13 indicator columns are
  highlighted a distinct fill color in the source file itself (confirmed by
  inspecting cell fills) — those are the ones surfaced as "Key Surveillance
  Indicators" on the dashboard (Non-Measles/Non-Rubella discard rate,
  Measles incidence/million, Rubella incidence/million, % sample collected,
  % adequate investigation, measles-related deaths). No target/threshold
  value exists anywhere in the workbook (confirmed by inspection) — the
  dashboard shows "Not specified in source data" rather than a guessed WHO
  benchmark; highest/lowest district per indicator is shown instead, genuinely
  sourced from the same per-district rows.
- **Part 1c (Monitoring / supervisory-visit pipeline)**: done for RCA (Rapid
  Convenience Assessment, child-level field vaccination-status spot checks)
  and Supervisory Checklist (facility-level visit compliance).
  `src/pipeline/{load_monitoring,clean_monitoring,indicators_monitoring,
  run_monitoring}.py` -> `data/processed/monitoring_summary.json` (+
  `monitoring_rca_cases.parquet` / `monitoring_supervisory_visits.parquet`).
  RCA and Supervisory Checklist are two genuinely separate reports (no shared
  key beyond District/Tehsil/UC) with no valid row-level join between them —
  they're never merged, only shown side by side in the same "Supervision" tab.
  **Both source files are HTML tables saved with a `.xls` extension, not real
  Excel binary/OOXML** (confirmed with `file`) — read via `pandas.read_html`,
  never `openpyxl`. Detected by column-name signature
  (`detect.py::detect_monitoring_file`, `RCA_COLUMN_SIGNATURE` /
  `SUPERVISORY_COLUMN_SIGNATURE`), the same "content, never filename"
  principle as Coverage/VPD sheet-name detection, just column-based since
  there are no sheets. Column access in `clean_monitoring.py` is positional
  (`RCA_COLUMNS`, `SUPERVISORY_FIELD_INDEX`), not name-based — the header
  text is long, punctuation-heavy, and one column decodes with a mangled
  apostrophe, same reasoning as `clean_vpd.py`'s positional MSL rename.
  Supervisory Checklist's 4 composite scores (Service Functionality,
  Monitoring System Quality, Operations Quality, Practices & Knowledge) are
  the source system's own pre-computed percentages, passed through
  unrecomputed ("trust the sheet", per the same rule as Coverage's UC-level
  Access/Utilisation) — **"Service Functionality" was 0% for every visit in
  the sample received**, traced to an entirely-unanswered UC-microplan
  checklist block (columns 107-132, 0 non-null values across all 63 visits),
  not a broken calculation; the dashboard shows this as an explicit caveat,
  not a hidden 0%. One real data-entry inconsistency found and flagged (not
  silently clipped): one visit recorded more functional SDD refrigerators
  than its own total unit count — surfaced as `inconsistent_visits` in
  `supervisory_cold_chain_summary`. RCA's zero-dose flag = Penta1 not
  received among children for whom Penta1 was actually assessed (WHO's
  standard zero-dose definition); "Not Applicable"/unassessed rows are
  excluded from that denominator, not counted as zero-dose. Only Abbottabad
  district data has been received so far for this domain — all Monitoring
  code aggregates by whatever districts are actually present, never a
  hardcoded list, so it will scale to full-province files unchanged.
- **Part 1d (WHO Supported Activities)**: done. `src/pipeline/who_activities.py`
  -> `data/processed/who_activities_summary.json`. Source file
  (`data/raw/WHO_EPI_May_2024_Highlights_Dashboard.xlsx`) is **not** a
  multi-period activity database — direct inspection showed it's a
  single-month (May 2024), single-duty-station (Malakand) field-monitoring
  highlights report covering 6 assigned KP districts, with 3 sheets that are
  3 different views of the SAME underlying report (`Sheet1` raw narrative,
  `Evidence & Findings` structured 11-row extraction, `WHO Highlights
  Dashboard` polished summary) rather than independent datasets. Detected by
  sheet-name signature (`REQUIRED_SHEETS` in `who_activities.py`, checked in
  `detect.py` before the other domains), same "content, never filename"
  principle as every other domain. That single-report shape drove a
  deliberately smaller dashboard scope than a generic activity-tracker
  template would suggest — built: Overview KPIs, Activity Distribution (by
  a manually verified `ACTIVITY_THEME` mapping, E01-E11, chosen over
  fuzzy/keyword inference given only 11 rows), Geographic Distribution
  (reuses the existing Coverage/Monitoring map infrastructure —
  `kp_districts.geojson`, `MAP_PROJECTION`, `renderSingleDistrictMap` — via
  a `DISTRICT_NAME_CANONICAL` dict mapping this source's adjective-first
  spelling, e.g. "Lower Chitral", to the project's established
  place-name-first spelling, e.g. "Chitral Lower"), a within-May-2024
  Timeline (explicitly labeled as such, not a multi-month trend), and
  verbatim narrative sections (Key WHO-Supported Results, District-Level
  Highlights, Priority System Gaps, Management Message) plus an
  auto-derived Key Insights list and a searchable Detailed Evidence Table.
  Deliberately **not** built, because the fields don't exist in the source:
  activity status breakdown, broad target-vs-achievement analysis (beyond
  the one source-stated measles-review KPI), multi-month trend, province
  comparison, implementing-partner filter. The map distinguishes a real 0
  (Bajaur — assigned to this duty station, zero evidence rows, but present
  in the Highlights sheet's own district list) from genuinely-out-of-scope
  (~30 other KP districts, absent entirely, rendered gray) by passing the
  Highlights sheet's assigned-district list into `build_district_map()`, not
  by treating every non-featured district the same way. The 4 headline KPIs
  appear in 2-3 independently-typed/located places in the source (text
  cells vs. a small numeric summary table vs. mentioned in the raw
  narrative) — cross-checked by `_reconcile_kpis()`, surfaced in
  `data_quality.headline_kpis_reconciled_against_summary_table_and_raw_narrative`.
  Other confirmed data-quality findings, all flagged rather than silently
  fixed: headline KPI cells are stored as Excel TEXT while the summary-table
  copies of the same values are real numbers
  (`numeric_fields_stored_as_text_in_source`); Bajaur has a narrative
  highlight but no evidence row
  (`districts_with_narrative_highlight_but_no_evidence_row`). Fully
  independent of Coverage/VPD/Monitoring/Indicator-Sheet, same architectural
  pattern as every other domain — a WHO-only upload still produces a working
  dashboard tab, and its absence doesn't block anything else. Excel export
  adds 5 sheets (WHO Activities Summary, WHO Evidence Data, WHO District
  Summary, WHO Activity Theme Summary, WHO Data Quality) to
  `EPI_Data_Export.xlsx` with the same freeze-panes/auto-filter/navy-header
  formatting as the rest of that workbook. PPT export needed zero
  WHO-specific code — the existing generic per-tab exporter
  (`exportActiveTabToPptx`) walks `.card` elements and produced a correct
  11-slide deck unaided; a small generic fix (skip content-free cards, e.g.
  a filters-only card) was made for all tabs, not just this one. 18 tests in
  `tests/test_who_activities.py`, pinned to real numbers from the source
  file.
- **VPD/Monitoring dashboard refinement round** (client feedback on specific
  screenshots, done): five targeted changes to existing domains, not new
  domains.
  1. **Diphtheria**: added a district spot map (`diphtheria_district_map` in
     indicators_vpd.py) — raw case count, not an incidence rate, since no
     population denominator exists for this disease (same reasoning as
     "Confirmed VPD decisions" below). Added an Age Group vs. Vaccination
     Status stacked bar (`diphtheria_age_dose_breakdown`): 5-year age band ×
     a coarser DPT dose-status grouping (Zero dose / 1-2 doses / 3+ doses /
     Unknown, regrouped from the existing `dose_status` field, no new raw
     data).
  2. **NNT**: "Cases (YTD)" relabeled to "Cases" (KPI card only covers this
     one line-list period, "YTD" was misleading). Added a district spot map
     (`nnt_district_map`) and two charts from the NNT line list: Mother
     Vaccination History (`tt_doses_mother`) and Place of Delivery
     (`delivery_place`). Two real data-quality findings surfaced, not
     smoothed over: every one of the 132 NNT cases received shows the exact
     same mother-TT-dose value ("0 doses") — shown as-is with an explicit
     caveat that this could be a genuine finding or a field-completeness
     gap, not silently treated as insightful variation; and `delivery_place`
     has a literal `"0"` value (9 rows) that isn't a real delivery-place
     category, normalized to "Not recorded" rather than shown as a bare 0
     (same "never show a placeholder 0 as a category" rule as Coverage's
     zero-target UCs).
  3. **Measles Outbreak Alert** (VPD Surveillance tab): the old
     quartile-based "Districts Requiring Action" table (relative
     Critical/Action/Monitor priority tiers) is gone, replaced by
     `measles_outbreak_alert_ucs` — a deterministic, documented rule (UC has
     a confirmed measles case in 3 or more of the last 4 epi weeks in the
     line list), explicitly labeled a rule-based screen for field
     follow-up, not a formal transmission-chain/genomic model (no
     contact-tracing data exists to build one) and not a confirmed-outbreak
     determination. Ships with an editable free-text box (reusing the
     existing `editableInsight` component) for province-issued outbreak
     response instructions.
  4. **District-wise (Measles Indicator Sheet)**: the old MSL-line-list
     -derived district table (suspected/measles-confirmed/rubella-confirmed)
     is replaced by a table sourced from the Measles Indicator Sheet
     workbook instead (`indicator_sheet_vpd.py::build_district_table`) —
     a separate source with its own district total (see Part 1b above),
     shown on its own, still never reconciled against the MSL line list.
  5. **Monitoring and Supervision tab, trimmed to a client-specified card
     set** (stays its own top-level tab, not merged into Coverage — asked
     and confirmed). RCA keeps: Summary, Antigen-wise Vaccination Status
     (now with a District/Activity-Theme-style dropdown filter reusing the
     source file's own "Age Group" categories — `0-11`/`12-23`/`24-52` in
     the data received, not a fabricated `0-11/12-23/24-59` scheme; the
     chart's height is now `antigens × 20px` rather than a flat "small",
     since a flat 260px genuinely broke legibility for all 19 antigens —
     found and fixed via direct screenshot inspection, not assumed),
     RCA Visits by Monitor (Cadre & Agency — `monitor_designation` /
     `monitor_agency`), Reasons for Non-Vaccination, and Area Profile.
     Removed: RCA Coverage Map, Age & Sex Profile, Verification Source &
     Social Mobilization, Daily Visit Trend. Supervisory Checklist keeps:
     Summary, Checklist Item Compliance, and Cold Chain & Vaccine Supply
     (now with real site-type KPI boxes added alongside it — 3 boxes,
     Fixed/Outreach/Mobile, not the 2 the client's note assumed, since the
     source data genuinely has 3 site-type categories, not fabricated down
     to match). Removed: Supervisory Coverage Map, Composite Compliance
     Scores card, standalone Site Type chart, Daily Visit Trend,
     District-wise Composite Scores table, Facility Rankings table. A new
     shared "Key Remarks from Monitors" card lists every non-blank remark
     from both RCA (`comments`, positional column) and Supervisory
     (`Remarks` / `Remarks if No:`, columns 33/67 — newly extracted into
     `SUPERVISORY_FIELD_INDEX`, previously unused) tagged with district/UC —
     explicitly a rule-based scan, not a live AI call (this dashboard is a
     fully offline static file). Confirmed by inspection: Supervisory's two
     remarks columns are entirely blank (0/63 rows) in the sample received,
     surfaced honestly as "no remarks recorded" rather than hidden; RCA's 31
     non-blank comments are mostly brief acknowledgements ("good work",
     "....") rather than substantive field observations, noted explicitly
     in the card's own caveat text rather than presented as if analyzed.
- **Second refinement round** (more client-annotated screenshots, done):
  - **Pertussis**: same "(YTD)" removal and district spot map as Diphtheria/
    NNT above. The KPI is relabeled "Suspected Pertussis" rather than just
    "Cases" -- the Pertussis line list has no lab-confirmation/classification
    field at all (confirmed by inspection, unlike Diphtheria/MSL), so every
    row genuinely is a suspected case with nothing to distinguish it from
    "confirmed" -- this is a terminology correction, not new data.
  - **Coverage Executive Overview**: "Antigen Requiring Attention" (and
    "Best Performing Antigen") no longer considers FIC a candidate --
    `coverage_summary.py::_best_worst_antigen` now excludes it specifically,
    since FIC is a composite indicator built from every other antigen, not a
    single vaccine dose, so ranking it alongside BCG/Penta1/etc. wasn't
    apples-to-apples (FIC is untouched everywhere else `DISTRICT_ANTIGENS`
    is used -- the antigen chart, target-gap dropdown, trend, maps -- since
    it's a legitimately tracked metric there). Added 4 new KPI cards, "UCs
    in Category 1-4", summed straight from the District sheet's own
    `cat1_count`..`cat4_count` columns (never averaged, never derived from
    the separate UC-level Category field) -- `build_executive_summary`'s new
    `uc_categorization` key. Real cross-sheet data-quality finding surfaced
    by this addition, not smoothed over: the District sheet's own summed
    Total UCs (1,305) doesn't match the UC Wise Analysis sheet's actual row
    count (1,376) -- both are genuine "trust the sheet" values from two
    different columns in the same workbook, not reconciled against each
    other, same as the Indicator Sheet's separate district total.
  - **Detailed District/Tehsil/UC Explorer**: the "UCs" column (total UC
    count) at District/Tehsil level is replaced with "LPUCs (Cat 3+4)" --
    low-performing UC count, computed client-side as `cat3_count +
    cat4_count` per row (both already-ingested raw fields, no new backend
    work needed). The "Category" column header is now level-specific
    ("District Category" / "Tehsil Category" / "UC Category") rather than a
    bare "Category" that could be confused between a district's own rollup
    category and a UC's own category shown further down the drill-down.
    The reported "dropdown not working" bug could not be reproduced --
    tested the search box, column sorting, and click-to-drill-down through
    District → Tehsil → UC under multiple sequences (after switching Monthly/
    Cumulative, after searching, after sorting, clicking the row vs. a cell)
    with zero errors every time; there is no `<select>` element in this
    table at all (only a search box and clickable rows) -- flagged back to
    the client rather than guessing at a fix for a bug that couldn't be
    observed.
  - **Weekly Trend** (VPD Surveillance): retitled "Weekly Measles Cases
    Trend of 2026" (client's handwritten title, typo corrected) and the
    description no longer says "and discarded" (client struck it through)
    -- confirmed with the client that the Discarded series itself should
    stay in the chart, only the wording changed.
  - **Antigen-wise Coverage Analysis reorder + MR2 -- declined, explained
    in-product**: the client asked to add MR2 "even if not given in the
    source file" and to reorder antigens into a fixed vaccination-schedule
    sequence including OPV/PCV/Rota, which aren't in this chart either.
    Neither was done: MR2 genuinely does not exist anywhere in the Coverage
    workbook (confirmed by inspecting every sheet's header row), and
    OPV/PCV/Rota exist only as UC-level percentages with no target (already
    covered honestly in section 2b, "Additional Antigens (Union Council
    Level Only)"), so including any of them here would mean fabricating a
    number -- against this project's foundational rule, restated in
    `coverage_summary.py`'s own module docstring from an earlier session.
    Separately, this chart is deliberately sorted by coverage performance
    (strongest to weakest, so the antigens needing attention surface first),
    not by vaccination-schedule sequence -- switching to a fixed order would
    change what the section is for, not just its wording, so that wasn't
    done unilaterally either. The section's own description text was
    expanded to state both of these facts explicitly, rather than leaving
    the gap unexplained for the next person reading the dashboard.
- **Third refinement round** (WHO Supported Activities tab, done):
  - Removed section 4, Field-Support Activity Timeline, entirely (chart,
    insight, and the now-dead `whoTimelineHtml`/`renderWhoTimelineChart`/
    `whoTimelineInsight` functions) -- the remaining sections renumbered
    2→3→4→5→6→7→8 so there's no gap where section 4 used to be.
  - "Key Insights" is now "🔎 7. Follow up action/Recommendation" and uses
    the same `editableInsight` click-to-edit component as every other
    narrative box on the dashboard, pre-filled with the same auto-derived
    insights as a starting draft. This needed a small `editableInsight`
    change: a new optional third `labelText` argument overrides the default
    "Insight (click to edit)" caption -- rendered as a separate, non-
    editable sibling element (a new `.insight-box-custom-label` div), never
    inside the contenteditable box itself, since `wireEditableInsights`
    saves that box's raw `innerText` to localStorage on blur and a label
    living inside it would get edited and saved along with the real
    content. Every other `editableInsight` call across the dashboard is
    unaffected (omits the new argument, keeps the original CSS
    `::before`-based label exactly as before).
  - "Key WHO-Supported Results" (now section 4) gained its own editable
    notes box (same component, empty prompt text) so findings can be added
    or modified in place, matching the pattern already used elsewhere
    (e.g. the Measles Outbreak Alert's province-instructions box).
- **Fourth refinement round** (done):
  - **WHO tab, Key WHO-Supported Results**: the editable notes box added in
    the third round is now explicitly labelled "Comments (click to edit)"
    (via `editableInsight`'s custom-`labelText` argument, added last round)
    instead of the generic "Insight (click to edit)" caption, since the
    client's ask was specifically for a place to "add comments" and the
    generic label wasn't reading as that feature.
  - **Diphtheria (VPD Surveillance tab)**: the small "Weekly trend" bar
    chart nested inside the main Diphtheria KPI card is gone, replaced in
    that same position by the Age Group vs. Vaccination Status chart
    (previously its own separate card immediately below the district map,
    added in the first refinement round) -- a straight swap, not an
    addition, so the age/dose breakdown no longer appears twice on the tab.
- **Fifth refinement round** (Monitoring & Supervision restructured into
  Service Delivery, done): this explicitly reverses the first round's
  AskUserQuestion answer ("keep as its own tab") per the client's own later
  instruction ("As discussed, the Monitoring & Supervision content should be
  treated as a subsection/component of Service Delivery").
  1. **Tab merge**: the standalone "Monitoring and Supervision" nav button
     and `#tab-supervision` panel are gone; `renderCoverage()` now always
     renders a Coverage-specific block (real content, or its existing
     "no Service Delivery data" placeholder) followed by a "Monitoring &amp;
     Supervision" `.section-divider` and the RCA/Supervisory content, in the
     same `#tab-coverage` panel -- restructured specifically to fix a real
     independence bug: the old `renderCoverage()` early-returned before ever
     reaching Monitoring content when Coverage data was absent, silently
     hiding RCA/Supervisory data that had, in fact, been uploaded. Now
     Coverage-absent-but-Monitoring-present (and vice versa) both render
     correctly, preserving the "every domain works independently" rule
     applied everywhere else in this project. `renderRcaSection` /
     `renderSupervisorySection` (their existing `{html, build}` pattern) are
     unchanged in shape, just invoked from `renderCoverage()` instead of a
     deleted `renderSupervision()`; the RCA age-group dropdown's change
     handler now calls `renderCoverage()` to re-render. The Overview tab's
     "no data" placeholder text and its default empty-state sentence were
     reworded to describe Monitoring &amp; Supervision as a subsection, not a
     tab (no functional change).
  2. **340 vs. 320 data-integrity finding, investigated per the client's
     explicit ask, confirmed correct (not a bug)**: the RCA Summary KPI's
     "Children assessed" (340) and the Zero-dose KPI's "assessed" denominator
     (320) are two different, both-genuine counts from
     `clean_monitoring.py`'s `is_penta1_assessed` field (Penta1 status is
     "Vaccinated" or "Not Vaccinated" -- excludes 20 rows where Penta1 is
     "Not Applicable"/blank). 340 = every child row in the RCA visit data;
     320 = the subset actually assessed for Penta1 specifically, the correct
     WHO-standard zero-dose denominator (a child RCA didn't assess for
     Penta1 can't contribute to a zero-dose rate). Not merged or
     reconciled -- they're genuinely different questions. The Zero-dose KPI
     card's caption was reworded from "X% of 320 assessed" to "X% of 320
     assessed for Penta1 (of 340 children assessed overall)" so the
     denominator difference reads as intentional on the dashboard itself,
     not as an unexplained discrepancy.
  3. **RCA Coverage Map re-added**: `rca_district_map()` (already computed
     server-side, unused in the UI since the first refinement round removed
     it) is rendered again as its own card, via the same
     `singleDistrictMapHtml`/`renderSingleDistrictMap` generic pair every
     other single-district map on this dashboard uses (Diphtheria/NNT/
     Pertussis/WHO) -- children-assessed is the mapped value, with RCA
     visits and zero-dose count in the hover tooltip. Only Abbottabad shows
     non-zero on the map in the data received so far, same "real 0 for
     every other district" convention as the other activity maps.
  4. **Cold Chain &amp; Vaccine Logistics -- two new site-type
     visualizations added**, alongside (not replacing) the existing
     Fixed/Outreach/Mobile KPI boxes: a Site-Type Distribution doughnut, and
     a new "Cold Chain Readiness by Site Type" grouped bar
     (backup-power-available % and stockout-in-last-3-months % per site
     type). Both use whatever site_type categories are actually present in
     the upload, never a hardcoded Fixed/Outreach/Mobile list. The second
     chart needed one new backend function,
     `supervisory_site_type_cold_chain()` in `indicators_monitoring.py` -- a
     genuine per-row cross-tab (site_type, backup_power_available, and
     stockout_last_3_months all live on the same visit row already), not a
     derived or estimated figure; a site type with zero answered rows for a
     field reports `pct: null`, never a fabricated 0%.
  5. **"Analyze Monitor Remarks" -- new feature, rule-based, no API call**:
     per the client's explicit instruction ("if it need any API or anything
     then dont do it... just analyse it yourself"), this is a deterministic
     keyword-rule scan run entirely client-side in the browser on demand (a
     button click, not automatic), never a live AI/LLM call -- consistent
     with this dashboard being a fully offline static file and with the
     first refinement round's identical "Key Remarks from Monitors"
     decision. `categorizeMonitorRemarks()` buckets each RCA/Supervisory
     remark into Key Insights or Key Issues by keyword match
     (`POSITIVE_REMARK_TERMS` / `ISSUE_REMARK_TERMS`), with a negation guard
     (`isNegatedBefore()`) so a remark like "no any issue found during
     session" isn't miscategorized as an issue just because it contains the
     word "issue" -- found and fixed via direct testing against the real
     remark text in this session's data, not assumed. Remarks matching
     neither list go to a neutral "other" bucket (never silently dropped --
     the count is surfaced in the panel's own text and the remarks
     themselves stay visible in the unchanged "Key Remarks from Monitors"
     table alongside this new panel). Output groups by District/UC in a
     table (so a flagged issue keeps its geographic context, per the
     client's requirement), and only lists a "Recommended Follow-up" line
     for a UC that actually has an issue-flagged remark -- no follow-up
     text is invented when none exists. Empty state ("No monitor remarks
     available for AI analysis.") shown directly, without a clickable
     button, when neither RCA nor Supervisory has any non-blank remark.
     Only remark text and district/UC/date values already present in the
     source rows are ever shown -- nothing generated or inferred, and no
     internal prompt/implementation detail is exposed (there is none; this
     is plain JS, not a model call).
  6. **Overview tab**: the Supervisory Checklist summary card's
     auto-insight sentence no longer cites `composite_scores` ("Lowest-
     scoring category: X") -- switched to the same "weakest checklist item"
     figure already used in the Supervisory section itself
     (`compliance_items[0]`), so the now-fully-unrendered Composite
     Compliance Score concept doesn't surface anywhere on the dashboard, not
     even indirectly in a summary sentence. `supervisory_composite_scores()`
     and `supervisory_facility_rankings()` themselves are left computed and
     in the JSON payload (unused by any UI element, like
     `daily_visit_trend` since the first refinement round) rather than
     deleted outright, matching this project's established "leave backend
     data intact, remove only display" convention -- deleting them would
     also mean deleting their pinned tests for no functional benefit.
  7. **Verified against the client's explicit removal checklist** (grepped
     the rebuilt `template.html`, zero matches for all of): Supervisory Map,
     Composite Compliance Score, District Composite Score, Facility
     Ranking, Fixed vs Outreach Site Graph, Daily Visit Trend. A Playwright
     sweep of all 5 tabs (Overview/Service Delivery/VPD Surveillance/WHO/
     Data Quality) confirmed zero console errors, the merged tab renders
     both Coverage and Monitoring content correctly, the RCA age-group
     dropdown and the new Analyze button both work with zero errors, and
     the PPT export of the merged Service Delivery tab produced 20 slides
     with zero empty ones (including the RCA map and Analyze Monitor
     Remarks card as their own slides). 149/151 tests passing (the same 2
     pre-existing sandbox-only Playwright-bulletin-PDF failures as every
     prior round, unrelated to this change).
- **Part 1e (Admin Activities)**: done, but with a different data shape than
  every other domain -- worth reading in full before touching this code.
  The source file received (`data/raw/Admin_Activities_Checklist.xlsx`, 1
  sheet, originally 21 rows x 6 columns, now 21 rows x 8 columns -- see the
  officer-rename note below) is a **blank per-officer administrative
  compliance checklist template**, not a case-level or activity-log
  dataset: 20 fixed administrative responsibilities (Logbook Submission,
  Monthly Report Submission/Compliance, DSO Mobility Claims, Financial/
  Payment Documentation, Procurement Requests, Programme Section Support,
  etc.) x originally 4 generic officer columns (`Officer 1`..`Officer 4`),
  plus a `Remarks / Evidence` column. Confirmed by direct cell-level
  inspection (values, fill colors, comments -- nothing hidden): every one
  of the officer cells literally contains the instructional string
  `"Yes/No/NA"` (telling
  whoever fills the sheet what to type), not a real answer, and every
  `Remarks / Evidence` cell holds a fixed descriptor of what evidence each
  task expects (e.g. `"Monthly"`, `"Quality & completeness"`), not an
  actual per-period remark. There is no date, district, UC, personnel name,
  agency, or activity-type field anywhere in the file. First reported to
  the user as a likely wrong upload; the user confirmed via two
  `AskUserQuestion` rounds that this genuinely is the source file, and
  explicitly chose to treat the Admin Activities tab as a **live, fillable
  checklist inside the dashboard** rather than a chart-driven analytics tab
  (there being no completed data to chart) -- the "Recommended" option
  offered, over a static read-only reference table or waiting for a
  different file.
  `src/pipeline/admin_activities.py` reads only the checklist's real
  STRUCTURE (task names, the officer column labels from the header row --
  never hardcoded to exactly 4 -- and each task's expected-evidence
  descriptor); `_normalize_officer_cell()` distinguishes the placeholder
  phrase (however spaced/cased) from a genuine single-word answer, so a
  future version of this file with real pre-filled Yes/No/N-A answers would
  be read as real starting data rather than ignored, with zero code change
  needed. Detected content-based (`detect.py::_is_admin_activities_workbook`,
  sheet name + A1 header text), same "content, never filename" principle as
  every other domain; wired into `run_weekly.py` and `webapp/app.py`
  identically to `who_activities.py`'s pattern.
  On the dashboard (`template.html::renderAdminActivities()`, tab
  positioned between WHO Supported Activities and Data Quality per the
  client's explicit nav-order instruction): 5 KPI cards (Total Tasks
  Tracked, Officers Tracked, Items Marked, Compliance Rate, Not Yet Marked),
  a status-distribution doughnut (Yes/No/N-A/Not yet marked), a By-Officer
  compliance table, and the full task x officer checklist as real `<select>`
  dropdowns (Yes/No/N-A) plus a "Reset checklist" button and an editable
  summary insight box -- every KPI/chart is computed live, client-side, from
  whatever has actually been selected. Selections are saved to this
  browser's `localStorage` (`epi-admin-status:<taskIndex>:<officerLabel>`),
  the same per-browser-only pattern every `editableInsight` box on this
  dashboard already uses, and persist across a page reload. Deliberately
  has no time trend, geographic map, or activity-type chart -- none of
  those fields exist in the source, so none are fabricated; the tab's own
  description text says so explicitly rather than leaving the gap
  unexplained. KPIs correctly read "0 marked" and every entry "not yet
  marked" and a "—" compliance rate on first load, which is the honest
  starting state, not a defect. 20 new tests in `tests/test_admin_activities.py`, including
  one asserting every source officer cell normalizes to "unanswered" (never
  a fabricated Yes/No/N-A) and a parametrized table for
  `_normalize_officer_cell()`'s placeholder-vs-real-answer logic. Verified
  with a Playwright sweep (nav order, zero console errors across all 6
  tabs, live KPI recompute on dropdown change, localStorage persistence
  across reload) and a PPT export check (5 slides, none empty).
- **Admin Activities officer rename** (done): the user provided the 6 real
  officer names to use in place of the 4 generic `Officer 1`..`Officer 4`
  placeholder labels: Dr Imtiaz Ali, Dr Imran Khan, Dr Haroon Ur Rashid,
  Dr Kazi Taimoor, Dr Sohrab Ali, Dr Asad Baig. Since 6 names didn't fit 4
  existing columns, asked which was intended (`AskUserQuestion`) -- user
  chose to expand to 6 officer columns rather than dropping 2 of the names
  or renaming only the first 4. Implemented by editing
  `data/raw/Admin_Activities_Checklist.xlsx` directly (`openpyxl`:
  `insert_cols` for the 2 new officer columns, header row set to the 6 real
  names, new cells filled with the same `"Yes/No/NA"` placeholder text as
  every other officer cell, `Remarks / Evidence` shifted to the new last
  column) -- **no pipeline code change was needed**, since
  `admin_activities.py` already reads officer labels/count dynamically from
  the header row rather than hardcoding 4 (see Part 1e above). Confirmed
  end-to-end: `run_admin_activities()` now reports "20 tasks x 6 officers"
  with the 6 real names as `officer_labels`, and the dashboard tab renders
  6 officer dropdown columns and a 6-row By-Officer table with zero code
  changes to `template.html`. Two tests in `test_admin_activities.py` that
  pinned the old 4-generic-name/count values were updated to the new real
  names/count (`test_officer_columns_match_source`,
  `test_summary_counts_match_source`); all 20 tests still pass, including
  the ones asserting every cell is still unanswered placeholder text (still
  true -- only the column headers changed, not any cell's answer state).
- **Overview tab rebuilt as a full executive-overview stack** (done): the
  user shared a screenshot of the existing "Measles & Rubella" KPI-card
  section (from the VPD Surveillance tab) as the pattern to replicate for
  every domain in the Overview tab. `renderOtherTabSummaries()` now renders,
  in a fixed order: Service Delivery Summary (existing prose, unchanged) ->
  a new combined "Monitoring and Supervision — Executive Overview" card
  (RCA's KPI row + Supervisory's KPI row together, replacing the old
  separate "RCA Summary"/"Supervisory Checklist Summary" prose cards) ->
  VPD Surveillance Summary (existing prose, unchanged) -> Measles & Rubella
  KPI row -> Diphtheria KPI row -> Pertussis KPI row -> Neonatal Tetanus KPI
  row -> WHO Supported Activities KPI row -> Admin Activities KPI row. Per
  the user's explicit instruction, the new sections are numbers-only (no
  new prose insight) -- exactly the same headline KPI cards already shown
  on that domain's own tab, not a rewritten summary.
  Structurally guarantees the Overview numbers can never drift from each
  domain's own tab: every KPI-card block that used to be built inline
  inside `renderSurveillance()`/`renderRcaSection()`/
  `renderSupervisorySection()`/`renderAdminActivities()` was first factored
  out into a shared function (`mslKpiRow`, `diphtheriaKpiRow`,
  `pertussisKpiRow`, `nntKpiRow`, `rcaKpiRow`, `supervisoryKpiRow`,
  `adminActivitiesKpiRow` -- later replaced by `adminSectionKpiRow` when
  Admin Activities was split into two sections, see below; `whoKpiRow`
  already existed), and BOTH the
  original tab and the new Overview card call the same function -- verified
  by comparing the Diphtheria KPI values rendered on the Service Delivery
  tab against the Overview tab byte-for-byte (167/35/91.6%/80.8%/1, exact
  match). The `#overview-tab-summaries` container switched from a `two-col`
  grid to a single-column stack (KPI-row cards need full width to lay out
  legibly) and its heading was renamed to "Executive Overview — All
  Sections". Two new CSS color variables added (`--who`, `--admin`) so the
  new WHO/Admin Activities cards get the same colored `disease-tag`
  treatment as every other domain card. Every new section independently
  gated on its own domain's data-available status (same per-domain
  independence rule as everywhere else) -- an Admin-Activities-only upload
  still shows every other section's "awaiting data" gap correctly, nothing
  fabricated. Verified with a Playwright sweep (zero console errors across
  all 6 tabs) and a PPT export check of the Overview tab (13 slides, none
  empty). 169/171 tests passing (the same 2 pre-existing sandbox-only
  Playwright bulletin-PDF failures as every prior round, unrelated).
- **Admin Activities split into Divisional Officer & Admin Compliance**
  (done): the user shared a second reference workbook
  (`Admin_Level_1.xlsx`) with a color-coding legend embedded in it -- a
  fill-color swatch in column J paired with a text label in column K on a
  few example rows (row 2: yellow swatch + "Divisional Officer"; row 4:
  green/theme-accent3 swatch + "Admin Section"; row 6: magenta swatch +
  "For both"; row 8: no-fill swatch + "Delete") -- confirmed by reading
  each cell's actual fill type/color/theme index directly, not guessed at.
  Applying that legend to each of the 20 task rows' own column-A fill color
  gave every task's section; exactly one task ("Monthly Report Compliance")
  was no-fill ("Delete") and was removed from the workbook entirely. The
  same reference file also renamed two travel-related tasks ("Duty Travel
  Requests" / "Travel Claims / Approval" -> "Travel Claims Submission" /
  "Travel Claims Processed"), adopted here. Result: 19 tasks -- 6
  "Divisional Officer", 12 "Admin Section", 1 "Both" ("Other Assigned
  Tasks"). `data/raw/Admin_Activities_Checklist.xlsx` was rebuilt with a
  new "Section" column holding these values (read dynamically by
  `admin_activities.py`, which also had to explicitly exclude this new
  column from its officer-column auto-detection) -- the 6 real officer
  names from the prior round were kept as-is, per the user's explicit
  reminder not to lose them.
  Tab renamed "Admin Activities" -> "Divisional Officer & Admin Compliance"
  (nav button, tab title, and every on-page reference). `renderAdminActivities()`
  restructured into two independent sub-sections, each with its own KPI
  row, status-distribution doughnut, by-officer table, and checklist table:
  "Divisional Officer Compliance" (6 tasks + the shared task = 7 rows) and
  "Admin Compliance" (12 tasks + the shared task = 13 rows). The shared
  task ("Other Assigned Tasks") is tracked as two fully independent
  checklist entries, one per section -- distinct `localStorage` keys via a
  new `sectionKey` component (`epi-admin-status:<section>:<taskIndex>:<officer>`,
  replacing the old two-part key) -- since a Divisional Officer's "other
  assigned tasks" and an Admin Section officer's are different real-world
  work despite sharing a label; verified live in the browser that marking
  it "Yes" under one section leaves the other section's copy unmarked. A
  small "shared task" badge on that row in both tables makes the
  relationship visible rather than silent. The Overview tab's combined card
  was updated to match (two mini KPI rows, "Divisional Officer Compliance"
  and "Admin Compliance", same pattern as the Monitoring & Supervision
  card). 23 tests in `test_admin_activities.py` (3 new: deleted-task
  absence, renamed-task presence, and full section-categorization
  matching the decoded legend for every one of the 19 tasks); 172/174
  tests passing overall (same 2 pre-existing sandbox-only failures).
  Verified with a Playwright sweep (zero console errors, correct nav
  label, correct row counts in both sections, live independent tracking of
  the shared task) and PPT export checks of both the Overview tab (13
  slides) and the new tab (10 slides), none empty.
- **Admin Compliance switched from per-officer to per-task tracking**
  (done): the user pointed out that the Admin Compliance checklist
  actually reflects one admin person's own work, not something meaningfully
  tracked per named officer -- asked to clarify the exact interaction model
  before rebuilding (`AskUserQuestion`, twice: which fields, and what a
  requested "Yes/No filter" should mean), confirmed: Divisional Officer
  Compliance is untouched (still 6 officer columns, Yes/No/N-A); Admin
  Compliance drops the officer columns entirely and instead tracks each
  task with two independent fields -- a 3-state completion status
  (`Completed` / `In Progress` / `Not Started`, chosen as clearer standard
  project-tracking language than the user's own literal "completed/not
  completed/partially completed" suggestion, which they invited improving
  on) and a separate `Verified by Supervisor` Yes/No sign-off, per the
  user's explicit answer that the second field means supervisor review, not
  e.g. evidence-attached. Neither field has a source-provided starting
  value (no such columns exist in the workbook), so both start unmarked --
  same "honest empty state, not a defect" principle as every other
  checklist field on this tab.
  New functions (`adminComplianceSummary`, `adminComplianceKpiRow`,
  `adminComplianceTableHtml`) replace the officer-based ones for this
  section only; new localStorage keys (`epi-admin-task-completion:<idx>`,
  `epi-admin-task-verified:<idx>`) since the per-officer key scheme no
  longer applies here. The Admin Compliance "By Officer" table and officer
  KPI card are gone (there's no officer dimension to break down anymore);
  its KPI row is now Tasks Tracked / Completed / In Progress / Not Started
  / Verified by Supervisor. Divisional Officer Compliance's own rendering
  path, KPI row, by-officer table, and Yes/No/N-A checklist are byte-for-
  byte unchanged. The Overview tab's combined card updated to show the new
  Admin Compliance KPI set alongside the untouched Divisional Officer one.
  The "shared task" ("Other Assigned Tasks") still appears in both
  sections, now tracked completely differently in each (per-officer
  Yes/No/N-A under Divisional Officer, per-task completion+verification
  under Admin Compliance) -- confirmed independent in the browser. Verified
  with a Playwright sweep (zero console errors, Divisional Officer section
  visually/structurally identical to before, Admin Compliance's new
  dropdowns work and update KPIs live) and PPT export checks of both the
  Overview tab (13 slides) and the tab itself (9 slides), none empty.
  172/174 tests passing (same 2 pre-existing sandbox-only failures;
  Python-side pipeline untouched this round, so no test changes needed).
- **Overview tab: Monthly/Cumulative period pills added, full audit pass**
  (done): the user asked for the same Monthly/Cumulative pill toggle
  already on the Service Delivery tab to also appear on Overview, so a
  user never has to leave Overview to change period. Implemented by
  reusing the exact same `state.coveragePeriodKind` state variable and
  `syncPeriodIdToCoverageKind()` sync function the Service Delivery tab
  already uses (per that function's own docstring: "One selector for the
  whole dashboard... rather than exposing a second, separate period
  control") -- Overview's pills are a second UI surface for the one shared
  state, not a second independent control. Clicking a pill on either tab
  updates both (`renderOverview()`/`renderCoverage()` each proactively
  re-render the other on change, mirroring the pattern already used for
  the Service Delivery pill).
  **Real bug found and fixed while building this**: the pill's `active`
  class toggled correctly on click, but the KPI numbers underneath it did
  not change -- `renderOverview()` read `provinceRow()`/`districtRows()`
  (both filtered by `state.periodId`) before anything had re-synced
  `state.periodId` from the newly-clicked `state.coveragePeriodKind`; the
  sync only happened as a side effect of the proactive `renderTab("coverage")`
  call *after* Overview had already rendered with the stale period. Fixed
  by calling `syncPeriodIdToCoverageKind(state.coveragePeriodKind)` at the
  very top of `renderOverview()`, before `provinceRow()` is read -- verified
  live that MR1 (73.0% -> 84.0%) and FIC (65.0% -> 80.0%) now genuinely
  change on pill click, not just the pill's own visual state.
  Followed by a full audit pass per the user's request: full pytest suite
  (172/174, same 2 pre-existing sandbox-only failures), a Playwright sweep
  exercising every interactive control across all 6 tabs (period pills,
  Explorer search/sort/drill-down, RCA age-group filter, Analyze Monitor
  Remarks button, WHO district/theme filters and search/reset, both
  Divisional Officer and Admin Compliance dropdowns and the reset button,
  editable insight boxes, Data Quality search) with zero console errors
  throughout, a grep sweep confirming no dead references remain to any
  previously-removed feature (Composite Compliance Score, Facility
  Ranking, Supervisory Map, WHO Timeline chart, the old officer-based
  Admin Compliance functions), a PPT export check of all 6 tabs (0 empty
  slides across 13/20/24/10/9/4 slides respectively), and a print/PDF CSS
  check confirming the new Overview pills follow the same
  only-show-the-active-pill-as-plain-text print convention as the
  Service Delivery pills, with no extra code needed since it's the same
  `.period-pill` CSS class. One pre-existing, non-regression cosmetic note
  observed (not fixed, out of scope): the nav bar's 6 tab labels start
  clipping below roughly 900px viewport width -- this dashboard has always
  been laid out for desktop/tablet review, never built mobile-first.
- **Part 2 (dashboard)**: done. `src/dashboard/{build.py,template.html}` ->
  `output/dashboard.html`, single self-contained file, Chart.js inlined
  (`src/dashboard/chart.umd.min.js`, downloaded once, not CDN-loaded).
  Coverage tab's Executive Overview is district-level (Top/Lowest Performing
  District, Districts Achieving Target Coverage, Districts Requiring
  Intervention -- UC-level detail lives only in its own "UC Compliance
  Analysis" section, never mixed into the executive cards). Right below it,
  a grid of one small choropleth map per antigen (plain inline SVG, no
  mapping library, no basemap tiles -- stays fully offline) using
  `src/dashboard/kp_districts.geojson` (District/ADM2 boundaries). **Replaced
  this session** with geometry traced from the user-provided reference map
  (`KP_MAP_1.pptx`) -- earlier used geoBoundaries.org (CC-BY 4.0), which only
  had 31 older, coarser boundary polygons, so every newer sub-split (Chitral
  Upper/Lower, Kohistan's 3-way split, Kurram's 2-way split, South
  Waziristan's 2-way split) had to share one polygon with its siblings,
  combined by summing raw counts. The pptx turned out to contain a real,
  separately labeled polygon for every one of KP's 36 current districts
  (confirmed by rendering its own vector shapes directly -- see session
  notes -- not by asking LibreOffice to export a preview, which fails in
  this sandbox); extracted with `python-pptx` (bezier curves flattened,
  Douglas-Peucker-simplified via `shapely` for embed size), 37 features
  total (36 real districts + Tor Ghar, a real district with no coverage data
  -- see below). `config.py`'s `DISTRICT_TO_BOUNDARY` is now a 1:1 identity
  mapping (kept, not dropped, since the map-builders key off it generically
  and it's still where a future shared-boundary case would go); the dict's
  own comment flags the one unconfirmed assumption (SW Wazir Belt / SW
  Mehsud Belt matched to the reference map's two South Waziristan shapes by
  adjacency to North Waziristan, not by an explicit label in the source).
  All 36 real districts are mapped with zero unmapped in Coverage, RCA, and
  Supervisory maps alike; verified exhaustive in
  `tests/test_coverage_summary.py`. One cosmetic-only artifact: a hairline
  gap between Kohistan Lower and Kolai Palas Kohistan, where the source map
  drew the Indus river as its own decorative shape between them (correctly
  excluded from extraction, since it isn't a district) -- invisible at
  normal dashboard scale, does not affect which data maps to which
  district.
- **Part 3 (bulletin)**: done for VPD surveillance (PDF + Excel annex + PPTX).
  `src/bulletin/{build.py,exports.py,template.html}` ->
  `output/Bulletin_Week_<N>_<year>.{pdf,xlsx,pptx}`. Rendered with Playwright
  (Chromium), one A4 page, matches the user-supplied sample bulletin layout.
  Word export not built (brief: only build on request, warn layout won't survive).
- 84 tests passing (`pytest tests/`), pinned to real numbers throughout.
- Run everything locally with `python run_weekly.py` from the project root.
- **Web app** (`webapp/app.py`, Flask): upload-and-download front end wrapping
  the exact same pipeline/dashboard/bulletin modules, with per-job temp
  directories for isolation between concurrent uploads. Containerized
  (`Dockerfile`) for deployment to Render.com (`render.yaml`) — see
  "Web app / hosting" below. No login (explicit user choice, no password) --
  job IDs are random UUIDs, the only isolation in place.

## Web app / hosting

- Every pipeline/dashboard/bulletin entry point now takes optional
  `raw_dir`/`processed_dir`/`output_dir`/`output_path`/`key_messages_path`
  parameters, defaulting to this project's `data/raw`, `data/processed`,
  `output/`, and `data/bulletin_inputs/key_messages.json` (unchanged CLI
  behaviour). The web app passes per-job temp paths instead so uploads never
  collide. Local CLI usage (`python run_weekly.py`) is unaffected.
- **Real bug caught during testing**: Werkzeug's `secure_filename()` replaces
  spaces and parentheses with underscores, which silently broke
  `config.infer_period()`'s regex (it needs the exact original filename,
  e.g. `"Dec 2025 Coverage Analysis (0-11).xlsx"`). Fixed with a minimal
  custom sanitizer (`webapp/app.py::_safe_upload_name`) that only strips path
  components / rejects traversal, without mangling the filename itself.
  Lesson: any future upload-handling code must NOT run uploaded EPI filenames
  through `secure_filename()`.
- **Coverage and VPD are now fully independent, in both directions** —
  Coverage and VPD each render an explicit "awaiting data" state
  (`VPD_AWAITING_STUB` / the equivalent coverage-empty path in
  `src/dashboard/build.py`) when the other wasn't uploaded, and
  `build_dashboard()` no longer hard-requires coverage data (it used to;
  a VPD-only upload built a bulletin but silently produced NO dashboard at
  all — found and fixed this session). The bulletin still hard-requires VPD
  data (it's VPD-only by design).
- **File type is detected from actual sheet-name content**
  (`src/pipeline/detect.py`), never from filename. The old approach ("VPD"
  in the filename = VPD, else assume coverage) broke the moment a real
  upload wasn't named the way this project's own sample files happen to be
  named. `find_raw_files`/`find_vpd_files` both use this now. A file that
  doesn't match either signature is reported to the user by name with a
  clear message, never silently dropped or guessed at. Monitoring uploads
  (RCA / Supervisory Checklist) go through a separate, analogous
  column-based detector (`detect_monitoring_file`) since those files are
  HTML tables saved as `.xls`, not real `.xlsx` workbooks with sheets — see
  Part 1c above.
- **Web upload UI is a single generic drop zone** (`webapp/templates/
  upload.html`), not separate Coverage/VPD slots — the old two-slot form
  required the user to know upfront which category each file belonged to,
  which the auto-detection makes unnecessary. `webapp/app.py`'s `generate()`
  classifies every uploaded file first, routes each to whichever pipeline
  applies, and always attempts the dashboard build regardless of what
  succeeded or failed elsewhere (previously gated behind `coverage_saved and
  not manifest["errors"]`, which also meant one unrelated bad file in a
  batch could silently block the dashboard for every good file alongside it
  — also fixed this session).
- **Excel data export** (`src/pipeline/export_excel.py` →
  `EPI_Data_Export.xlsx`): a multi-sheet workbook built from the same
  `data/processed/*` the dashboard reads (never recomputed, same
  never-disagree principle as the bulletin). One sheet per actually-
  processed component only — Coverage District/UC Data, Coverage KPI/
  Antigen Summary, VPD Surveillance Summary, VPD District Breakdown — never
  an empty or fabricated sheet for a component that wasn't uploaded.
- **PDF export is client-side** (`window.print()` + a `@media print`
  stylesheet in `template.html`), not server-rendered — it captures exactly
  what's currently on screen (active tab, period pill, antigen/district
  selection) since there's no server round-trip that knows the viewer's
  client-side state. Works identically on a `dashboard.html` opened fully
  offline, not just through the web app. The interactive controls themselves
  (nav, selects, pill buttons) are hidden when printing, but what they were
  set to stays visible as plain text — a `.print-only` label mirrors the
  period dropdown's selected option, and the active period-pill is
  re-styled as plain bold text instead of being hidden with the others.
- Deployment target: Render.com, Docker runtime (`python:3.12-slim` +
  `playwright install --with-deps chromium` + gunicorn). Chosen because
  Playwright needs a real Chromium install, which rules out the smallest
  free/serverless tiers that don't run full containers.
- **Not yet done** (as of this write-up): actually deploying to get a live
  URL. That requires the user to create a GitHub repo (push this local git
  repo to it) and a Render account, then connect the two — account creation
  isn't something this assistant can do on the user's behalf. The Flask app
  itself has been tested and confirmed working locally end-to-end (upload →
  processing → dashboard + bulletin download, ~15s for a full 3-file run);
  the Docker build itself has NOT been tested locally (no Docker available
  on this machine) — Render's own build step will be the first real test of
  the Dockerfile.

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
| `data/raw/RCA_Report_2.xls` | 1 HTML table, 50 columns, 340 child rows (34 RCA visits) | Aug 2026, Abbottabad district only | See Part 1c above. |
| `data/raw/Supervisory_Checklist_Report.xls` | 1 HTML table, 137 columns, 63 visit rows | Aug 2026, Abbottabad district only | See Part 1c above. |
| `data/raw/Indicator_SheetMeasles.xlsx` | 7 sheets, one per year (2020-2026) | 2026 sheet used (all 37 real districts + Provincial Total) | See Part 1b above (indicator_sheet_vpd.py). |
| `data/raw/WHO_EPI_May_2024_Highlights_Dashboard.xlsx` | 3 sheets (`Sheet1`, `Evidence & Findings`, `WHO Highlights Dashboard`) | Single month, May 2024, Malakand duty station (6 assigned districts) | See Part 1d above (who_activities.py). 3 sheets are 3 views of one report, not independent data. |
| `data/raw/Admin_Activities_Checklist.xlsx` | 1 sheet (`Admin Activities`), now 19 task rows x 6 named officer columns + a Section column | No period -- a blank compliance checklist template, not a dated record | See Part 1e above (admin_activities.py) and the later "Divisional Officer & Admin Compliance" round for the 6-officer rename and 2-section split. User-confirmed genuine source; built as a live, browser-fillable checklist, not a chart. |

AFP (within VPD) has **not** been provided yet — see "Confirmed VPD decisions" below.

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
