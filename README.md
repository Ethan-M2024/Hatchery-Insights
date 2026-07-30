# Washington Hatchery Escapement Report Insights

Every salmon and steelhead counted back to a Washington state hatchery rack or trap,
**starting from the 1998–99 season and running to the present**, pulled out of WDFW's
PDF reports and turned into something you can actually explore, print and export.

**[▶ Open the live dashboard](https://ethan-m2024.github.io/Hatchery-Insights/)**

Washington publishes this record as PDFs: one *Final Hatchery Escapement Report* a year,
and a new in-season report most Thursdays. Read one at a time they answer a single
question each. Read together, back to 1998, they show which runs are recovering and which
are not, when fish arrive and whether that is shifting, what happens to them at the rack,
and how any one hatchery compares with the rest of the state.

This repository holds every one of those reports, parsed and reconciled, and rebuilds
itself daily as WDFW publishes more. Nothing is hand-entered and no figure is estimated:
every number traces to a published report, and each one is checked against WDFW's own
totals before it ships. See [Accuracy](#accuracy).

---

## One command

Same command on macOS and Windows, whichever you prefer:

```
python3 run.py              # macOS / Linux — open the dashboard
py run.py                   # Windows — open the dashboard

python3 run.py --update     # fetch the newest WDFW reports, rebuild, then open
python3 run.py --check      # re-run the accuracy audit on the data already here
python3 run.py --help       # every option
```

Opening needs **no install and no internet**. The built page ships in this
repository and carries its own data. Only `--update` needs the PDF libraries, and
`run.py` sets those up by itself the first time you ask for it, in a private `.venv`
that touches nothing else on your machine.

If you would rather not use a terminal, double-click instead:

| | macOS | Windows |
|---|---|---|
| **Just look at it** | `Open Dashboard (Mac).command` | `Open Dashboard (Windows).bat` |
| **Pull in new reports** | `Update Dashboard (Mac).command` | `Update Dashboard (Windows).bat` |

The buttons run exactly the same code as the command line, so neither can drift from
the other.

You can also open `docs/index.html` directly — it is one self-contained file you can
email, put on a shared drive, or keep on a USB stick.

### It will not take over your machine

Reading PDFs is pure CPU work. By default the updater leaves two cores free and never
uses more than four, so your laptop stays usable and does not thermally throttle. On a
build machine with nothing else to do, `--jobs 8` lifts the cap.

## Update it with the newest reports

WDFW posts a new weekly report most Thursdays. `python3 run.py --update` pulls them
in, or double-click:

**Mac** — **`Update Dashboard (Mac).command`**
**Windows** — **`Update Dashboard (Windows).bat`**

The first run sets up a private Python environment for you (about a minute). After
that an update takes **under a minute**, because the repository already contains
every row extracted so far — it only downloads and reads reports that are genuinely
new. When it finishes it re-runs the full accuracy audit and opens the dashboard.

<details>
<summary>If your Mac says the file "cannot be opened because it is from an unidentified developer"</summary>

Right-click the `.command` file → **Open** → **Open**. macOS only asks once.
If double-clicking does nothing at all, open Terminal in this folder and run
`chmod +x *.command`.
</details>

<details>
<summary>If Windows SmartScreen warns you</summary>

Click **More info** → **Run anyway**. The `.bat` file is plain text — open it in
Notepad if you want to read exactly what it does first.
</details>

<details>
<summary>Prefer the command line?</summary>

```bash
pip install --require-hashes -r requirements.lock.txt   # SHA-256 verified
python src/pipeline.py             # update, validate, rebuild, open
python src/pipeline.py --check     # run the accuracy audit only, no network
python src/pipeline.py --full      # ignore all caches, rebuild from the PDFs (~25 min)
python src/pipeline.py --no-open   # skip launching the browser
```
Python 3.9+ on Windows, macOS or Linux. The only direct dependency is
`pdfplumber`; the lock file pins its whole tree by hash.
</details>

### How long anything actually takes

| What you're doing | How long |
|---|---|
| Open the dashboard | **instant** — no Python, no internet, no setup |
| Pull in this week's new reports | **~13 seconds** |
| First run ever (builds a Python environment) | ~1 minute, once |
| Re-read all ~700 PDFs from scratch | ~35 minutes — **and you never need to** |

That last row is the only slow path, and it exists for one reason: if the *parsing
code* changes, every already-extracted row is stale. Three things mean it never lands
on you:

- The repository ships the extracted rows, so nothing is re-read that has not changed.
- The pipeline fingerprints the parser. It re-reads a PDF only when the code that
  reads PDFs actually changed — not when a chart, a label, or the page changed.
- When a parser change *is* pushed, a GitHub Action does the 35 minutes on GitHub's
  machines and commits the result. Your next update just picks it up.

## Getting the data without cloning anything

Every file is served straight from the repository, so scripts and notebooks can read
it directly — no clone, no build, no key:

```python
import pandas as pd
BASE = "https://raw.githubusercontent.com/Ethan-M2024/Hatchery-Insights/main/data/"

rows   = pd.read_csv(BASE + "annual_raw.csv.gz")   # every facility × season record
weekly = pd.read_csv(BASE + "raw.csv.gz")          # every weekly in-season snapshot
```

| File | What it is |
|---|---|
| `data/annual_raw.csv.gz` | facility × stock × species × season, as published |
| `data/raw.csv.gz` | every row of every weekly in-season report |
| `data/dashboard_data.json` | the compact payload the dashboard itself reads |
| `data/facility_geo.json` | hatchery coordinates, county, WRIA, waterbody |
| `data/manifest.json` | URL, SHA-256 and fetch time of every source PDF |
| `data/build_info.json` | which parser version produced the rows |

These are refreshed by the weekly Action, so they stay current whether or not anyone
runs anything locally.

---

## What's in the dashboard

| Tab | What it shows |
|---|---|
| **Overview** | Statewide totals by season, one line per species; region and hatchery-vs-wild composition |
| **Species** | Small multiples with each species' peak season; spring/summer/fall/winter runs broken out |
| **Facilities** | The busiest racks, a sparkline for every rack at once, a profile and history for any one of them, and a picker to compare up to six |
| **Run timing** | How the season in progress is tracking against the range of past seasons, plus cumulative arrival curves by week — when the fish actually show up, and how each season compares |
| **Egg take** | Egg take against the Future Brood Document goal, and the programmes furthest below it |
| **At the rack** | What became of every fish — spawned, passed upstream, surplussed, or dead before spawning — plus pre-spawn mortality, eggs per spawner, and wild-origin share |
| **Trends** | Mann-Kendall trend tests with Sen's slope, each season against its trailing ten-season mean, run-timing shift, brood-year return per egg, and a jack-based forecast |
| **Map** | Every hatchery placed on Washington, sized by return and coloured by its largest run, plus a watershed (WRIA) rollup |
| **Programs** | Which stocks are handled at which racks, and the network of fish moved between hatcheries |
| **Data** | All rows, sortable and searchable, with exports |

Every chart has a **Table** button showing the same numbers, and the whole thing works
in light and dark mode, on a phone, and on paper.

## Exports

From the **Data** tab, respecting whatever filters you have set:

- **Excel** (`.xlsx`) — real workbook with a second sheet recording the source, filters and definitions
- **Word** (`.docx`) — formatted table with the source notes
- **CSV** — UTF-8 with a BOM, so Excel opens it cleanly
- **GeoJSON** — for ArcGIS, QGIS, Leaflet or Mapbox
- **KML** — placemarks for Google Earth, scaled by return size
- **Print / PDF** — a proper print stylesheet

Four scopes: every row, by season and species, by facility, or facility locations only.
All generated in your browser — nothing is uploaded anywhere.

---

## Accuracy

WDFW prints a `TOTAL STATEWIDE` line for each species in each season. The rows this
project extracts must sum to it **exactly**, column by column:

| Column | Result |
|---|---|
| adults trapped | **562 / 562 exact** |
| jacks trapped | **562 / 562 exact** |
| adults received | **562 / 562 exact** |
| jacks received | **562 / 562 exact** |
| egg take | **562 / 562 exact** |
| adults released | 561 / 562 (one contradiction inside the source itself) |
| jacks released | **562 / 562 exact** |
| adults net / jacks net | see *source quirks* below |

Regional subtotals: **977 / 977 exact.**

`src/validate.py` runs ten checks and **fails the build** if any of them break, so a
bad update cannot quietly ship. The others cover agreement between the weekly and
annual series, monotonic run curves, unbroken season coverage, value plausibility,
coordinates landing inside Washington, source-file checksums, and data freshness.

`tests/test_ui.py` drives the real page in a browser: seven tabs at four widths in
both colour themes, then downloads every export and **opens it** with `openpyxl`,
`python-docx`, a JSON parser and an XML parser — a file that downloads but will not
open still fails.

```bash
pip install playwright openpyxl python-docx && playwright install chromium
python tests/test_ui.py
```

### Source quirks

Each of these was traced back to the original PDF by hand. They are properties of
WDFW's reports, not of this extraction:

- **The "trapped less released" (net) columns are not a subtraction.** WDFW derives
  them separately, and their *own* published statewide totals fail
  `trapped + received − released = net` in about 30% of species-seasons. The validator
  proves this by applying the identity to numbers this code never touches. Those
  columns are exported exactly as printed and drive no chart here.
- **2024–25 Cutthroat / Resident Coastal** — the Columbia River regional total says
  124 released; the single facility row beneath it says 227.
- **1999–2000 Coho** — the printed jacks subtotal is 22,916; the rows above it sum to
  22,917.
- **Publication 02636** serves an unrelated abalone status review at its plain URL;
  the escapement report is at `_0`. The fetcher reads each cover page and rejects
  anything that is not an escapement report, so this self-heals.
- **Two weekly Cutthroat seasons (2021, 2022) are mis-segmented** — cutthroat are
  reported year-round at some racks, so the cumulative count never resets far enough
  to mark a season boundary. The build drops any weekly season whose total diverges
  more than 35% from the annual final rather than draw a curve that is not one
  season's run, and reports what it dropped.

### Analytical notes

- **Pre-spawn mortality** is deaths before spawning over fish trapped, from the weekly
  reports. Sockeye run near 24% statewide — a thermal-stress signature — against 4% for
  coho. Rates on fewer than 2,000 fish are excluded from the ranking; a rate on a small
  denominator is noise.
- **Trend tests** use Mann-Kendall, which is rank-based and so assumes neither a
  straight line nor normal errors. Sen's slope gives the magnitude. Results are banded
  honestly: p<0.01, p<0.05, and p<0.10 shown as *weak* rather than dressed up as
  significant.
- **Run timing is measured per run type, not per species.** Summer and winter
  steelhead arrive months apart; a combined median lands in November and describes
  neither. Split out, summer steelhead reach halfway on 9 August and winter steelhead
  on 27 December. Spring, summer and fall Chinook are separated the same way. The
  combined series is still offered — it is what the annual reports total — but it is
  labelled *all runs* and the note says why a run type is the better unit.
- **Run-timing curves** are indexed by calendar week of the March-to-March season, so
  a week on the axis is the date it claims to be. An earlier version indexed weeks from
  the date each run was *detected*, which drifts by months between species — that put
  the coho median in late May instead of late October. Seasons whose run was not
  observed from the beginning are excluded, and the axis extends as far as the species
  actually runs (coho finish in November; winter steelhead are still arriving in May).
- **Run-timing shift** measures the date by which half a season's fish had arrived,
  anchored to 1 March so runs crossing the new year stay comparable — calendar
  day-of-year would read 20 Dec → 5 Jan as a 349-day swing. Seasons not observed from
  the start of the run are excluded, which is why the 2012–13 fragment does not appear.
  This is arrival at a trap, so it reflects when the rack was operated as well as when
  the fish moved.
- **Jack forecasting** is only offered where it beats the naive alternative of carrying
  this season forward. On the current record that is coho (r=0.64 vs 0.46) and sockeye
  (0.53 vs 0.00); for Chinook and steelhead persistence is as good, and the table says
  so rather than hiding it.

### Notes on the newer views

- **Season progress** compares the run under way against the 10th–90th percentile of
  completed seasons *at the same week*, so a part-season is never measured against
  whole ones. It hides itself, with an explanation, when a run has not started yet or
  there are too few past seasons to form a range.
- **Brood-year return per egg** divides adults returning three, four and five years
  later by the egg take that produced them. It is a productivity measure, not a
  survival rate: the reports do not say how many of those eggs were released, nor
  which returning fish came from which hatchery.
- **Transfers** are recovered from the comment beside the shipped count ("Shipped to
  Speelyai Hatchery"), because no column names the destination. A movement recorded
  without a comment is not counted, so this is a floor rather than a total.
- **Watershed colouring** on the map groups racks by WRIA and draws the area their own
  points enclose. WRIA boundaries are not published with the escapement data, so that
  shape is an extent, not a border.

### Reading the numbers

**Escapement** here means adults returning to a hatchery rack or trap — *not* the
total run to a river. Fish that spawn below the rack, are harvested, or pass a trap
while it is not in use are not counted. **Jacks** are early-maturing males, counted
separately. **Origin** is H (hatchery), W (wild) or M (mixed); mixed rows usually
carry egg take rather than fish. **Egg-take goals** come from the Future Brood
Document and are absent (`NA`) on many rows — those are excluded from attainment
rather than treated as zero. A **season** is a spawning cycle running approximately
March to the following March. Weekly figures are preliminary; annual figures are final.

---

## How it fits together

```
Open Dashboard (Mac).command / (Windows).bat    open docs/index.html, nothing else needed
Update Dashboard (Mac).command / (Windows).bat  set up Python if needed, then run the pipeline

docs/index.html      the dashboard — one self-contained file, no external requests
data/                extracted rows (gzipped CSV), the payload, checksums, locations
src/pipeline.py      orchestrator: fetch, parse, geocode, build, validate, assemble
src/parse.py         weekly in-season report parser
src/parse_annual.py  annual report parser — handles all three layout eras
src/geo.py           joins hatchery names to WDFW's GIS facility layer
src/build_data.py    normalises names, folds era spellings, emits the payload
src/validate.py      the accuracy audit
src/assemble.py      injects the payload into the template
src/template.html    the page itself
tests/test_ui.py     browser test suite
```

`data/manifest.json` records the URL, SHA-256 and fetch time of every source PDF, so
an update can tell what actually changed. The PDFs themselves (about 120 MB) live in
`.cache/` and are not tracked — they are re-downloadable at any time and the extracted
rows are what matter.

Facility coordinates, county, WRIA and waterbody come from WDFW's
**HatcheryLikeFacilities** GIS layer, joined by name. All 101 hatcheries matched; a
handful map a counting point (a dam ladder, a weir) onto its parent hatchery.

## Does it update itself?

**The hosted dashboard: yes.** `.github/workflows/refresh.yml` runs every morning,
pulls in anything WDFW has posted, re-runs the full audit, rebuilds the page and
commits it. GitHub Pages caches for ten minutes, so a refresh after that picks up the
new build automatically — no action from anyone. If the audit fails nothing is
committed and the run goes red, so a bad build cannot quietly replace a good one.
The build is deterministic, so a day with no new report commits nothing at all.

This also means new runs appear on their own. The "runs under way" table is computed
at build time from whatever is in the data, so when coho start returning in autumn
they show up without anyone touching the code.

**A copy you downloaded: no.** It is a file; it shows what it contained when it was
built. That is deliberate — it works offline, on a USB stick, attached to an email.
Double-click the updater to refresh it, and the page tells you how old it is either
way: a green dot when it is current with WDFW, amber with an explanation once the
newest report in the copy is more than three weeks old.

**Neither can be fresher than WDFW.** They publish weekly, usually Thursdays. Nothing
here parses PDFs in a browser, so "live" means "as current as the last published
report", and the daily job exists to make sure that is never more than a day late.

## Security

This project downloads files from the internet and runs them through a PDF parser, so
it was audited as if the source site were hostile. Ten issues were found and fixed —
including a path-traversal flaw that would have let a tampered WDFW page write to
`~/.ssh/authorized_keys`. Downloads are now restricted to an HTTPS host allow-list
with redirect checking and a size ceiling, filenames are reduced to characters that
cannot escape a folder, dependencies are pinned by SHA-256, and the page ships a
strict Content-Security-Policy.

Full write-up, including residual risks: **[SECURITY.md](SECURITY.md)**.

The dashboard makes **no network requests**, stores **nothing** in your browser, and
generates every export locally. Nothing is uploaded anywhere.

## Source and licence

Data: [WDFW Hatchery Escapement Reports](https://wdfw.wa.gov/fishing/management/hatcheries/escapement)
and the WDFW HatcheryLikeFacilities GIS layer. WDFW data is public record; this
project is not affiliated with or endorsed by WDFW.

Code released under the [MIT licence](LICENSE).
