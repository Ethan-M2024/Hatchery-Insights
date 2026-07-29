# WDFW Hatchery Escapement Dashboard

Every salmon and steelhead counted back to a Washington state hatchery rack or trap,
**1998–99 through 2024–25**, pulled out of WDFW's PDF reports and turned into
something you can actually explore, print and export.

**[▶ Open the live dashboard](https://ethan-m2024.github.io/wdfw-hatchery-escapement/)**

Built from 27 annual *Final Hatchery Escapement Reports* and 705 weekly in-season
reports — 9,788 facility records and 166,769 weekly observations. Every number
reconciles against WDFW's own published totals; see [Accuracy](#accuracy).

---

## Just open it

You do **not** need Python, an internet connection, or any setup to look at the data.

1. Click the green **Code** button above → **Download ZIP**
2. Unzip it
3. Double-click **`Open Dashboard (Mac).command`** or **`Open Dashboard (Windows).bat`**

That opens the dashboard in your browser with all 27 seasons already in it.
(Or just open `docs/index.html` directly — it is one self-contained file you can
email, put on a shared drive, or keep on a USB stick.)

## Update it with the newest reports

WDFW posts a new weekly report most Thursdays. To pull them in:

**Mac** — double-click **`Update Dashboard (Mac).command`**
**Windows** — double-click **`Update Dashboard (Windows).bat`**

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
pip install -r requirements.txt
python src/pipeline.py             # update, validate, rebuild, open
python src/pipeline.py --check     # run the accuracy audit only, no network
python src/pipeline.py --full      # ignore all caches, rebuild from the PDFs (~25 min)
python src/pipeline.py --no-open   # skip launching the browser
```
Python 3.9+ on Windows, macOS or Linux. The only dependency is `pdfplumber`.
</details>

---

## What's in the dashboard

| Tab | What it shows |
|---|---|
| **Overview** | Statewide totals by season, one line per species; region and hatchery-vs-wild composition |
| **Species** | Small multiples with each species' peak season; spring/summer/fall/winter runs broken out |
| **Facilities** | The busiest racks, per-facility history, and a picker to compare up to six hatcheries side by side |
| **Run timing** | Cumulative arrival curves by week — when the fish actually show up, and how each season compares |
| **Egg take** | Egg take against the Future Brood Document goal, and the programmes furthest below it |
| **Map** | Every hatchery placed on Washington, sized by return and coloured by its largest run, plus a watershed (WRIA) rollup |
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

## Automatic weekly refresh

`.github/workflows/refresh.yml` runs every Friday morning, pulls in whatever WDFW
posted that week, re-runs the audit and commits the result. If the audit fails,
nothing is committed and the run is marked red. You can also trigger it by hand from
the **Actions** tab.

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
