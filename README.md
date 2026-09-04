# KP EPI Dashboard & Bulletin System — How to Use It

Two ways to use this. Pick whichever fits:

- **Web app** (recommended for sharing with colleagues) — open a link in a
  browser, upload the Excel files, download the dashboard and bulletin. No
  install, no terminal. See "Using the web app" below. Deployment setup for
  this is in `DEPLOY.md`.
- **Local command** — for the person running it on their own PC. See "The
  weekly routine (local command)" below.

## Using the web app

Once deployed (see `DEPLOY.md`), share the Render URL with anyone on the
team who needs it. They:

1. Open the link.
2. Drop in one or more Excel files — a Coverage workbook, a VPD surveillance
   line list, or both. **Neither is required and neither depends on the
   other**: each file is identified automatically from its actual sheet
   names (not its filename), so a Coverage-only upload gets a working
   Coverage dashboard with the Surveillance tab showing "awaiting data," a
   VPD-only upload gets the Surveillance dashboard + bulletin with the
   Coverage tab showing "awaiting data," and uploading both gets everything.
   A file that isn't recognized as either is reported clearly on the results
   page — it doesn't block the files that were recognized.
3. Optionally paste in this week's Key Messages (one per line) — leave blank
   to use the default set.
4. Click **Generate dashboard & bulletin**.
5. On the results page: `dashboard.html` (always built, whatever combination
   was uploaded), the `Bulletin_Week_N_year.pdf/.xlsx/.pptx` files (only if a
   VPD file was uploaded — the bulletin is VPD-only by design), and
   `EPI_Data_Export.xlsx` — a multi-sheet export of the processed data
   (district/UC tables, KPI summary, antigen summary, VPD summary) with a
   sheet only for whatever was actually uploaded.

The dashboard itself also has a **Download PDF** button (top right) that
prints exactly what's currently on screen — whichever tab, period, and
antigen/district selection you have open — since it's a plain browser print,
not a server round-trip. Works the same way on a `dashboard.html` opened
completely offline, not just through the web app.

Nothing is saved permanently on the server — each upload gets its own
temporary workspace that's cleared automatically after 24 hours. There is
**no login** on this tool (by design, at the project owner's request) — treat
the URL itself as the only thing controlling access, and don't post it
somewhere public if that's a concern.

## The weekly routine (local command)

For running it yourself on one PC without the web app.

### One-time setup (already done on this machine)

Python and all required libraries are already installed in this project
folder. Nothing to install to use it week to week.

### Steps

1. **Drop the new Excel file(s) into `data/raw/`.**
   - Coverage file (monthly or cumulative EPI coverage export) — same 4-sheet
     format as before (District / Tehsil / UC Wise Analysis - Coverages / UC
     Wise Analysis - Difference).
   - VPD line list — identified automatically from its sheet names (MSL,
     Diphtheria, NNT, Pertussis line lists), not from the filename — it no
     longer needs to contain the word "VPD".
   - Never rename or edit files already in `data/raw/` — old files can stay
     there, the system reads the latest ones by content, not by deleting
     anything.

2. **(Optional) Edit the Key Messages.**
   Open [data/bulletin_inputs/key_messages.json](data/bulletin_inputs/key_messages.json)
   in Notepad and edit the 4 bullet points under `"messages"` — these are the
   only part of the bulletin a human writes by hand, they're never
   auto-generated. Save the file.

3. **Run one command.**
   Open a terminal in this folder and run:
   ```
   python run_weekly.py
   ```
   It prints its progress as it goes and takes under a minute. If something
   in a new file doesn't match the expected format, it will stop with a
   plain-English error message rather than a mess of technical output —
   read that message, it tells you what to check.

4. **Collect the outputs from the `output/` folder:**
   - `dashboard.html` — open in any web browser (double-click it). Works
     without internet, and you can email it as an attachment.
   - `Bulletin_Week_<N>_<year>.pdf` — the printable/emailable weekly bulletin.
   - `Bulletin_Week_<N>_<year>_annex.xlsx` — the same numbers as plain Excel
     tables, for anyone who wants to re-cut or double-check them.
   - `Bulletin_Week_<N>_<year>.pptx` — a short slide deck for review meetings.

Each run overwrites the previous `dashboard.html`, but bulletin files are
named by week number so old weeks' bulletins won't get overwritten (as long
as you don't run the same week twice — if you do, it overwrites that week's
files, not other weeks').

## Using the dashboard (`dashboard.html`)

- **Overview tab** — province-wide coverage snapshot: BCG/Penta/MR1/FIC %
  with red/amber/green coloring, and which districts are doing best/worst.
- **Coverage tab** — click a district to drill into its tehsils, click a
  tehsil to drill into its UCs. Click a UC row to expand its full detail.
  Search box filters by name. Switch the period dropdown (top-right) between
  the monthly and cumulative coverage snapshots.
- **Surveillance tab** — measles-rubella, diphtheria, pertussis and NNT
  numbers and trends. AFP shows "awaiting data" until an AFP file is added.
- **Supervision tab** — will populate once supervisory-visit data is added;
  shows "awaiting data" for now.
- **Data Quality tab** — every row the system had to flag or exclude while
  cleaning the raw files (wrong denominators, impossible values, duplicate
  entries, etc.), with the reason for each. This is the audit trail — if a
  number looks surprising, check here first.

## Using the bulletin PDF

It's laid out to match your existing weekly bulletin design. Two things are
handled honestly rather than guessed:
- Rows that need a population figure (incidence rates) show **N/A*** with a
  footnote, because that data isn't available yet — not a fabricated number.
- The AFP section says **"awaiting data"** until an AFP line list is
  supplied — same reasoning.

## What's not live yet

- **AFP surveillance** — needs an AFP line-list file (like the measles or
  diphtheria ones). Once dropped into `data/raw/`, it'll appear automatically
  on the next run — no rebuild needed.
- **Supervisory visits** — needs a sample file first so the format can be
  confirmed, then it slots in the same way.
- **Incidence rates** (per million/per 100,000) — needs a district population
  figure. Once you have one, it can be added as a config file.

## If something goes wrong

Every script fails loudly with a specific message telling you what it
expected vs. what it found — it will not silently produce a wrong number.
If you see an error you don't understand, save the full terminal output and
share it along with the file you were trying to load.
