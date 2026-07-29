"""Turn the parsed CSVs into one compact JSON payload for the dashboard.

Strings are interned into dictionaries and rows become integer arrays so the whole
27-season record fits inside a single self-contained HTML page.
"""
import csv, json, re, os, collections
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
from paths import open_text



def i(v):
    if v in ('', None, 'None'):
        return 0
    try:
        return int(v)
    except ValueError:
        return 0


def opt(v):
    if v in ('', None, 'None'):
        return None
    try:
        return int(v)
    except ValueError:
        return None


# ---------- facility name normalisation across eras ----------
# The 1998-99 and 1999-2000 reports use short title-case names ("Kendall Creek");
# every later report uses the Adult Report Database form ("KENDALL CR HATCHERY").
# Strip the facility-type suffix from both so the same site joins across 27 seasons.
TYPE_WORD = re.compile(
    r'\b(HATCHERY|HATCHRY|HATCH|PONDS?|REARING|REARIN|TRAP|FCF|SALMON)\b')


# "RINGOLD SPRINGS HATCHERYPriest" — the facility name and the stock beside it are
# extracted as one token when the glyphs nearly touch. Facilities are upper case and
# stocks are title case, so the seam is recoverable.
RUN_TOGETHER = re.compile(r'([A-Z]{2,})([A-Z][a-z])')


def split_run_together(name):
    """Cut a facility name where the stock name was glued onto it.

    "RINGOLD SPRINGS HATCHERYPriest" is one token in the PDF. The facility is upper
    case and the stock title case, so the seam is unambiguous — and everything from
    the seam onward belongs to the stock, not the rack.
    """
    n = name or ''
    m = RUN_TOGETHER.search(n)
    if m:
        n = n[:m.start(2)]
    # a title-case tail after an all-caps name is stock text too
    return re.sub(r'(?<=[A-Z])\s+[A-Z][a-z]\w*(?:[-\s]\w+)*\s*$', '', n).strip()


def norm_fac(name):
    n = re.sub(r'\s+', ' ', split_run_together(name).strip().upper())
    n = n.replace('.', '').replace(',', '').replace("'", '')
    n = n.replace('COWLTIZ', 'COWLITZ').replace('VOIGHTS', 'VOIGHT')
    n = re.sub(r'\bCREEK\b', 'CR', n)
    n = re.sub(r'\bRIVER\b', 'R', n)
    n = re.sub(r'\bLAKE\b', 'LK', n)
    n = re.sub(r'\bSPRINGS\b', 'SPRING', n)
    n = TYPE_WORD.sub(' ', n)
    return re.sub(r'\s+', ' ', n).strip()


def facility_names(path=None):
    """The facility names the payload will actually key on, after era-name aliasing
    but before the GIS merge — this is what geo.py must be given, so its output is
    keyed the same way build_annual() looks it up."""
    with open_text(path or paths.RAW_ANNUAL) as fh:
        rows = [r for r in csv.DictReader(fh)
                if r.get('table') != 'broodstock' and r['row_type'] == 'facility']
    raw = {norm_fac(r['facility']) for r in rows}
    alias = link_aliases(raw)
    return sorted({alias.get(n, n) for n in raw if n})


def link_aliases(names):
    """Map short early-era names onto the longer canonical ones ('MINTER' ->
    'MINTER CR') when the short name is an unambiguous token-prefix of exactly one."""
    canon = sorted(names, key=lambda s: (-len(s.split()), s))
    alias = {}
    for n in names:
        toks = n.split()
        if not toks:
            continue
        hits = [c for c in canon
                if c != n and c.split()[:len(toks)] == toks]
        if len(hits) == 1:
            alias[n] = hits[0]
    # collapse chains (A->B->C)
    for k in list(alias):
        seen = {k}
        v = alias[k]
        while v in alias and v not in seen:
            seen.add(v)
            v = alias[v]
        alias[k] = v
    return alias


RACE_FIX = {'na': 'NA', 'typen': 'Type N', 'types': 'Type S', 'searun': 'Sea-Run',
            'sea-run': 'Sea-Run', 'bull tr na': 'NA', 'bull na': 'NA',
            'bull trout na': 'NA', 'trout na': 'NA', ': general na': 'NA',
            'residentcoastal': 'Resident Coastal', 'anadromouscoastal': 'Anadromous Coastal',
            'winter late': 'Winter-Late', 'winterlate': 'Winter-Late', '': 'NA'}


def norm_race(r):
    key = (r or '').strip().lower()
    return RACE_FIX.get(key, (r or 'NA').strip() or 'NA')


def norm_species(s):
    """'Chinook Fall' / 'FALL CHINOOK SALMON' / 'Chinook / Fall' -> (group, race)."""
    if not s:
        return ('Unknown', 'NA')
    t = re.sub(r'\s+', ' ', s.strip())
    t = re.sub(r'\bCont\.?$', '', t, flags=re.I).strip()
    t = re.sub(r'\bSALMON\b|\bTROUT\b(?! )', '', t, flags=re.I).strip()
    t = t.replace('/', ' ').strip()
    tl = t.lower()
    groups = ['chinook', 'coho', 'chum', 'sockeye', 'pink', 'steelhead', 'kokanee',
              'cutthroat', 'rainbow', 'brown', 'dolly', 'bull', 'whitefish',
              'sturgeon', 'sucker', 'tiger', 'brook', 'lake trout', 'atlantic',
              'walleye', 'burbot', 'grayling', 'char']
    g = next((x for x in groups if x in tl), None)
    if g == 'dolly' or g == 'bull':
        grp = 'Dolly/Bull Trout'
    elif g:
        grp = {'brown': 'Brown Trout', 'rainbow': 'Rainbow', 'cutthroat': 'Cutthroat',
               'brook': 'Brook Trout', 'lake trout': 'Lake Trout'}.get(g, g.title())
    else:
        grp = t.title() or 'Unknown'
    race = re.sub(re.escape(g), '', tl, flags=re.I).strip().title() if g else ''
    race = re.sub(r'\s+', ' ', race).strip(' -') or 'NA'
    return (grp, race)


SALMONID_ORDER = ['Chinook', 'Coho', 'Chum', 'Sockeye', 'Pink', 'Steelhead',
                  'Cutthroat', 'Kokanee', 'Rainbow', 'Dolly/Bull Trout']


def weekly_facility_names(path=None):
    """Facility names that appear in the weekly reports.

    Seasons rebuilt from weekly data can involve racks the annual reports have not
    listed yet, and those still need coordinates.
    """
    path = path or paths.RAW_WEEKLY
    if not os.path.exists(path):
        return set()
    out = set()
    for r in csv.DictReader(open_text(path)):
        n = norm_fac(r.get('facility'))
        if n:
            out.add(n)
    return out


def gis_merge(names):
    """Names that the WDFW GIS layer resolves to the same physical site are the same
    hatchery under a different report-era spelling (SOL DUC / SOLDUC). Fold them onto
    the longest-serving name so a facility's history is continuous."""
    if not os.path.exists(paths.FACILITY_GEO):
        return {}
    geo = json.load(open(paths.FACILITY_GEO))
    groups = collections.defaultdict(list)
    for n in names:
        g = geo.get(n)
        if g:
            groups[g['gis_name']].append(n)
    merge = {}
    for site, fs in groups.items():
        if len(fs) < 2:
            continue
        keep = max(fs, key=lambda f: (len(f), f))
        for f in fs:
            if f != keep:
                merge[f] = keep
    return merge


def build_annual():
    with open_text(paths.RAW_ANNUAL) as fh:
        rows = [r for r in csv.DictReader(fh)
                if r.get('table') != 'broodstock' and r['row_type'] == 'facility']
    alias = link_aliases({norm_fac(r['facility']) for r in rows})
    merged = gis_merge({alias.get(norm_fac(r['facility']), norm_fac(r['facility']))
                        for r in rows})
    facs, stocks, sps, races, regions = {}, {}, {}, {}, {}

    def idx(d, k):
        if k not in d:
            d[k] = len(d)
        return d[k]

    recs, totals = [], []
    for r in rows:
        grp, race = norm_species(r['species_race'])
        race = norm_race(race)
        fac = norm_fac(r['facility'])
        fac = alias.get(fac, fac)
        fac = merged.get(fac, fac)
        if not fac:
            continue
        rec = [
            int(r['season'][:4]),
            idx(sps, grp), idx(races, race),
            idx(regions, (r['region'] or 'Unknown')),
            idx(facs, fac),
            idx(stocks, (r['stock'] or '').strip()),
            {'H': 1, 'W': 2, 'M': 3}.get((r['bo'] or '').strip().upper(), 0),
            i(r['adults_trapped']), i(r['jacks_trapped']),
            i(r['adults_received']), i(r['jacks_received']),
            i(r['eggtake']),
            opt(r['eggtake_goal']) if r['eggtake_goal'] not in ('', None) else -1,
            i(r['adults_released']), i(r['jacks_released']),
            i(r['adults_net']), i(r['jacks_net']),
        ]
        recs.append(rec)

    def inv(d):
        out = [None] * len(d)
        for k, v in d.items():
            out[v] = k
        return out

    return {
        'cols': ['year', 'sp', 'race', 'region', 'fac', 'stock', 'bo',
                 'adults', 'jacks', 'adults_rcv', 'jacks_rcv', 'eggtake',
                 'egg_goal', 'adults_rel', 'jacks_rel', 'adults_net', 'jacks_net'],
        'facilities': inv(facs), 'stocks': inv(stocks), 'species': inv(sps),
        'races': inv(races), 'regions': inv(regions),
        'rows': recs,
        # how a raw facility string became one of the names above; preliminary rows
        # must resolve through exactly the same map or the same rack appears twice
        '_facmap': {'alias': alias, 'merged': merged},
    }


SEASON_START_MONTH = 3  # WDFW season runs ~March -> March


def build_weekly(annual_totals=None):
    """Weekly reports are cumulative season-to-date, so one report = one snapshot.
    Sum rows within a report to get the statewide figure, bucket reports into
    season-weeks, then take the running max so each curve is monotone cumulative."""
    if not os.path.exists(paths.RAW_WEEKLY):
        return None
    import datetime
    snap = collections.defaultdict(int)   # (sp, season, week) -> adults in that report
    per_report = collections.defaultdict(int)   # (sp, report_date) -> adults
    rep_meta = {}
    seen_files = set()
    for r in csv.DictReader(open_text(paths.RAW_WEEKLY)):
        rd = r['report_date']
        if not rd:
            continue
        try:
            d = datetime.datetime.strptime(rd.split(', ', 1)[1], '%B %d, %Y').date()
        except (ValueError, IndexError):
            continue
        seen_files.add(r['source'])
        grp, _ = norm_species(r['species'])
        per_report[(grp, d)] += i(r['adult_total'])
        rep_meta[d] = True

    # The nominal March turnover is fuzzy: an early-March report still carries the
    # closing prior season. Find each season boundary from the data instead — the
    # week the running cumulative collapses back toward zero.
    byspecies = collections.defaultdict(list)
    for (grp, d), total in per_report.items():
        byspecies[grp].append((d, total))

    # Cut the report stream into runs at each reset, then label each run by the year
    # its median fish arrived. Anchoring on the start date mislabels species that go
    # unreported for months (pink salmon, which return only every other year).
    runs = []   # (grp, start_date, {week: cumulative})
    for grp, pts in byspecies.items():
        pts.sort()
        cur = None
        for d, total in pts:
            if cur is None or (cur['peak'] > 200 and total < cur['peak'] * 0.4):
                cur = {'grp': grp, 'start': d, 'peak': total, 'wk': {}, 'dates': {}}
                runs.append(cur)
            cur['peak'] = max(cur['peak'], total)
            wk = (d - cur['start']).days // 7
            if 0 <= wk <= 60:
                cur['wk'][wk] = max(cur['wk'].get(wk, 0), total)
                cur['dates'][d] = total

    bysp = collections.defaultdict(dict)
    for run in runs:
        wks = run['wk']
        if not wks:
            continue
        end = max(wks.values())
        if end <= 0:
            continue
        med = next((w for w in sorted(wks) if wks[w] >= end * 0.5), 0)
        mid = run['start'] + datetime.timedelta(days=med * 7)
        season = mid.year if mid.month >= SEASON_START_MONTH else mid.year - 1
        run['season'] = season
        prev = bysp[(run['grp'], season)]
        for w, v in wks.items():
            prev[w] = max(prev.get(w, 0), v)

    sps = sorted({k[0] for k in bysp})
    out = []
    for (grp, season), wks in sorted(bysp.items()):
        run, series = 0, []
        for w in sorted(wks):
            run = max(run, wks[w])
            series.append([w, run])
        if run < 500 or len(series) < 12:   # partial or noise-level, not a run curve
            continue
        end_v = series[-1][1]
        med_wk = next((w for w, v in series if v >= end_v * 0.5), series[0][0])
        run_start = next((r['start'] for r in runs
                          if r.get('season') == season and r['grp'] == grp), None)
        med_date = (run_start + datetime.timedelta(days=med_wk * 7)) if run_start else None
        out.append({'sp': sps.index(grp), 'season': season, 'w': series,
                    'med': med_date.isoformat() if med_date else None,
                    # Days from 1 March of the season year to the median fish. Calendar
                    # day-of-year cannot be used: chum and coho run across the new year,
                    # so 20 Dec (354) to 5 Jan (5) would read as a 349-day swing.
                    'med_off': ((med_date - datetime.date(season, SEASON_START_MONTH, 1)).days
                                if med_date else None),
                    # Was the run observed from its beginning? The weekly archive opens
                    # in January 2013, so the first season is a tail fragment whose
                    # "median" is really just its first report. A median arrival date
                    # means nothing unless the start of the run was seen.
                    'from_start': 1 if series[0][1] <= end_v * 0.15 else 0})
    # A season's curve is only comparable once the run is over. Reporting stops at
    # different weeks for different species, so completeness is judged by whether a
    # later season was observed for that species — a reset proves the run ended.
    last_season = {}
    for s in out:
        last_season[s['sp']] = max(last_season.get(s['sp'], -1), s['season'])
    for s in out:
        s['done'] = 1 if s['season'] < last_season[s['sp']] else 0

    # Cross-check each curve against the final annual number for the same species and
    # season. A curve whose total is far off has almost certainly been mis-segmented
    # (a species reported year-round never drops far enough to trigger a reset), so
    # drop it rather than draw a run-timing curve that is not one season's run.
    dropped = []
    if annual_totals:
        keep = []
        for s in out:
            a = annual_totals.get((sps[s['sp']], s['season']), 0)
            ratio = (s['w'][-1][1] / a) if a >= 1000 else None
            if ratio is not None and not (0.7 <= ratio <= 1.35):
                dropped.append((sps[s['sp']], s['season'], round(ratio, 2)))
            else:
                keep.append(s)
        out = keep

    used = sorted({s['sp'] for s in out})
    remap = {old: n for n, old in enumerate(used)}
    for s in out:
        s['sp'] = remap[s['sp']]
    # the date span each species' season occupies, and the report date on which that
    # season's cumulative count peaked — that snapshot is the season's breakdown
    windows = collections.defaultdict(list)
    peaks = {}
    for run in runs:
        if 'season' not in run:
            continue
        last = max(run['wk']) if run['wk'] else 0
        windows[run['grp']].append(
            (run['season'], run['start'],
             run['start'] + datetime.timedelta(days=last * 7 + 6)))
        if run.get('dates'):
            # the date a report was actually published, not start + 7n: WDFW posts on
            # Thursdays but skips weeks, so the arithmetic date can miss every report
            peaks[(run['grp'], run['season'])] = max(run['dates'],
                                                     key=lambda d: run['dates'][d])

    return {'species': [sps[o] for o in used], 'series': out,
            'n_reports': len(rep_meta), 'n_files': len(seen_files),
            'dropped': dropped,
            'windows': {k: [(a, b.isoformat(), c.isoformat()) for a, b, c in v]
                        for k, v in windows.items()},
            'peaks': {f'{g}|{sn}': d.isoformat() for (g, sn), d in peaks.items()}}


def build_preliminary(windows, after_year, newest_report, peaks=None):
    """Facility-level rows for seasons that have finished but have no final report yet.

    A weekly report is a cumulative snapshot of the whole state, so the honest way to
    get a facility breakdown is to take *one* snapshot — the report where that
    species' season-to-date count peaked — and read its rows. Summing per-facility
    maxima across different reports does not work: the same rack reappears under
    slightly different stock spellings from week to week, and each variant keeps its
    own running total, which inflated the 2024-25 season by 74% when tested against
    the published final.

    Decomposing the one snapshot whose total is already validated against the annual
    reports means the parts can never disagree with the whole.
    """
    import datetime
    if not os.path.exists(paths.RAW_WEEKLY) or not peaks:
        return [], None

    def finished(season):
        return datetime.date(season + 1, SEASON_START_MONTH, 1) < newest_report

    # (group, season) -> the report date whose cumulative total was highest
    wanted = {(g, sn): d for (g, sn), d in peaks.items() if sn > after_year}
    by_date = collections.defaultdict(set)
    for (g, sn), d in wanted.items():
        by_date[d].add(g)

    rows = collections.defaultdict(lambda: [0, 0, 0, 0])
    for r in csv.DictReader(open_text(paths.RAW_WEEKLY)):
        rd = r.get('report_date') or ''
        try:
            d = datetime.datetime.strptime(rd.split(', ', 1)[1], '%B %d, %Y').date()
        except (ValueError, IndexError):
            continue
        if d not in by_date:
            continue
        grp, race = norm_species(r.get('species'))
        if grp not in by_date[d]:
            continue
        season = next(sn for (g, sn), dd in wanted.items() if g == grp and dd == d)
        stock = (r.get('stock') or '').strip()
        m = re.search(r'-\s*([HWM])\s*$', stock)
        bo = {'H': 1, 'W': 2, 'M': 3}.get(m.group(1), 0) if m else 0
        stock_name = re.sub(r'-\s*[HWM]\s*$', '', stock).strip()
        key = (season, grp, norm_race(race), norm_fac(r.get('facility')), stock_name, bo)
        v = rows[key]
        v[0] += i(r.get('adult_total'))
        v[1] += i(r.get('jack_total'))
        v[2] += i(r.get('eggtake'))
        v[3] += i(r.get('live_released'))

    done, running = [], []
    for (season, grp, race, fac, stock, bo), v in rows.items():
        (done if finished(season) else running).append(
            {'year': season, 'sp': grp, 'race': race, 'fac': fac, 'stock': stock,
             'bo': bo, 'adults': v[0], 'jacks': v[1], 'eggtake': v[2], 'released': v[3]})
    return done, running


FATE_FIELDS = ['adult_total', 'jack_total', 'mortality', 'surplus',
               'live_released', 'lethal_spawned', 'live_spawned', 'eggtake']


def build_fate(peaks, facmap=None):
    """What became of the fish at each rack, per facility, species and season.

    The weekly reports carry the full disposition — how many were spawned, passed
    upstream, surplussed, and how many died before spawning — but only the trapped
    count was ever used. Each season is read from the single report where that
    species' cumulative count peaked; measured against the season maximum of every
    field, that snapshot loses nothing (0.0% on all but sockeye mortality, 8.5%),
    and it guarantees the parts sum to a total already validated against the
    published annual reports.
    """
    import datetime
    if not os.path.exists(paths.RAW_WEEKLY) or not peaks:
        return None
    by_date = collections.defaultdict(set)
    for (g, sn), d in peaks.items():
        by_date[d].add(g)

    alias = (facmap or {}).get('alias', {})
    merged = (facmap or {}).get('merged', {})

    acc = collections.defaultdict(lambda: [0] * len(FATE_FIELDS))
    for r in csv.DictReader(open_text(paths.RAW_WEEKLY)):
        rd = r.get('report_date') or ''
        try:
            d = datetime.datetime.strptime(rd.split(', ', 1)[1], '%B %d, %Y').date()
        except (ValueError, IndexError):
            continue
        if d not in by_date:
            continue
        grp, _ = norm_species(r.get('species'))
        if grp not in by_date[d]:
            continue
        season = next(sn for (g, sn), dd in peaks.items() if g == grp and dd == d)
        fac = norm_fac(r.get('facility'))
        fac = merged.get(alias.get(fac, fac), alias.get(fac, fac))
        v = acc[(season, grp, fac)]
        for k, f in enumerate(FATE_FIELDS):
            v[k] += i(r.get(f))

    sps, facs, rows = {}, {}, []

    def idx(d, k):
        if k not in d:
            d[k] = len(d)
        return d[k]

    for (season, grp, fac), v in sorted(acc.items()):
        if not any(v):
            continue
        rows.append([season, idx(sps, grp), idx(facs, fac)] + v)

    def inv(d):
        out = [None] * len(d)
        for k, n in d.items():
            out[n] = k
        return out

    return {'cols': ['year', 'sp', 'fac', 'trapped', 'jacks', 'mortality', 'surplus',
                     'released', 'lethal_spawned', 'live_spawned', 'eggtake'],
            'species': inv(sps), 'facilities': inv(facs), 'rows': rows}


def build_environment(facilities):
    """River and ocean conditions, indexed to line up with the facility list."""
    if not os.path.exists(paths.ENVIRONMENT):
        return None
    with open_text(paths.ENVIRONMENT) as f:
        env = json.load(f)
    tj, fj = env.get('temp_join', {}), env.get('flow_join', {})
    gauges = env.get('gauges', {})

    METRICS = ['t_mean_summer', 't_max7', 't_days_18', 't_days_20',
               'q_mean', 'q_min7', 'q_max']
    rows = []          # [facility index, season, ...metrics]
    joins = []         # per facility: which gauges, how far
    for n, fac in enumerate(facilities):
        t, q = tj.get(fac), fj.get(fac)
        joins.append([
            t['station'] if t else None, t['km'] if t else None,
            t['matched_on'] if t else None,
            q['station'] if q else None, q['km'] if q else None,
            q['matched_on'] if q else None])
        seasons = set()
        for j in (t, q):
            if j:
                seasons |= set((gauges.get(j['site'], {}).get('seasons') or {}).keys())
        for sn in sorted(seasons):
            tv = (gauges.get(t['site'], {}).get('seasons', {}).get(sn, {}) if t else {})
            qv = (gauges.get(q['site'], {}).get('seasons', {}).get(sn, {}) if q else {})
            vals = [tv.get(m) if m.startswith('t_') else qv.get(m) for m in METRICS]
            if any(v is not None for v in vals):
                rows.append([n, int(sn)] + vals)

    return {'cols': ['fac', 'year'] + METRICS,
            'join_cols': ['temp_station', 'temp_km', 'temp_match',
                          'flow_station', 'flow_km', 'flow_match'],
            'joins': joins, 'rows': rows,
            'ocean': env.get('ocean', {}), 'meta': env.get('meta', {})}


def latest_weekly_report_date():
    """Date of the most recent weekly report actually present in the data."""
    import datetime as _dt
    if not os.path.exists(paths.RAW_WEEKLY):
        return None
    best = None
    for r in csv.DictReader(open_text(paths.RAW_WEEKLY)):
        rd = r.get('report_date') or ''
        try:
            d = _dt.datetime.strptime(rd.split(', ', 1)[1], '%B %d, %Y').date()
        except (ValueError, IndexError):
            continue
        if best is None or d > best:
            best = d
    return best.isoformat() if best else None


def build_geo(facilities):
    """Attach WDFW GIS coordinates and watershed context, indexed to match rows."""
    if not os.path.exists(paths.FACILITY_GEO):
        return None
    geo = json.load(open(paths.FACILITY_GEO))
    keys = ['lat', 'lon', 'gis_name', 'type', 'owner_class', 'operator',
            'county', 'wria', 'waterbody', 'system', 'active', 'elev_ft']
    out = []
    for f in facilities:
        g = geo.get(f)
        out.append([g.get(k) for k in keys] if g else None)
    return {'cols': keys, 'rows': out,
            'n': sum(1 for x in out if x),
            'source': ('WDFW FP_FishMaps/HatcheryLikeFacilities '
                       '(geodataservices.wdfw.wa.gov)')}


def merge_preliminary(A, prelim):
    """Fold preliminary rows into the annual table, reusing its string dictionaries."""
    ci = {c: n for n, c in enumerate(A['cols'])}
    idx = {'sp': {v: i for i, v in enumerate(A['species'])},
           'race': {v: i for i, v in enumerate(A['races'])},
           'fac': {v: i for i, v in enumerate(A['facilities'])},
           'stock': {v: i for i, v in enumerate(A['stocks'])},
           'region': {v: i for i, v in enumerate(A['regions'])}}

    def intern(kind, key, store):
        if key not in idx[kind]:
            idx[kind][key] = len(store)
            store.append(key)
        return idx[kind][key]

    # a facility's region is stable, so take it from its own history
    region_of = {}
    for r in A['rows']:
        region_of.setdefault(r[ci['fac']], r[ci['region']])
    unknown = intern('region', 'Unknown', A['regions'])

    fm = A.get('_facmap', {})
    alias, merged = fm.get('alias', {}), fm.get('merged', {})
    known = set(A['facilities'])

    def canon(name):
        n = alias.get(name, name)
        n = merged.get(n, n)
        if n in known:
            return n
        # an unseen weekly spelling: attach it to an existing rack when one clearly
        # contains it, rather than minting a duplicate facility
        hits = [k for k in known if k and (k.startswith(n + ' ') or n.startswith(k + ' '))]
        return hits[0] if len(hits) == 1 else n

    added = 0
    for p in prelim:
        fac = intern('fac', canon(p['fac']), A['facilities'])
        row = [p['year'],
               intern('sp', p['sp'], A['species']),
               intern('race', p['race'], A['races']),
               region_of.get(fac, unknown),
               fac,
               intern('stock', p['stock'], A['stocks']),
               p['bo'],
               p['adults'], p['jacks'], 0, 0,
               p['eggtake'], -1,
               p['released'], 0,
               max(0, p['adults'] - p['released']), 0]
        A['rows'].append(row)
        added += 1
    return added


def main():
    data = {'annual': build_annual()}
    A = data['annual']
    ci = {c: n for n, c in enumerate(A['cols'])}
    totals = collections.defaultdict(int)
    for r in A['rows']:
        totals[(A['species'][r[ci['sp']]], r[ci['year']])] += r[ci['adults']]
    wk = build_weekly(totals)
    if wk:
        data['weekly'] = wk
    # Seasons that have run their course but whose final report is not out yet get
    # preliminary rows from the weekly series, so the dashboard reaches the present.
    facmap = A.get('_facmap', {})
    final_through = max(r[0] for r in A['rows'])
    prelim_seasons, running_season = [], None
    if wk and wk.get('windows'):
        newest = latest_weekly_report_date()
        import datetime as _d
        peaks = {(k.rsplit('|', 1)[0], int(k.rsplit('|', 1)[1])):
                 _d.date.fromisoformat(v) for k, v in (wk.get('peaks') or {}).items()}
        done, running = build_preliminary(
            wk['windows'], final_through,
            _d.date.fromisoformat(newest) if newest else _d.date.today(), peaks)
        if done:
            merge_preliminary(A, done)
            prelim_seasons = sorted({p['year'] for p in done})
        if running:
            yr = max(p['year'] for p in running)
            cur = [p for p in running if p['year'] == yr]
            by_sp = collections.defaultdict(lambda: [0, 0, 0])
            for p in cur:
                e = by_sp[p['sp']]
                e[0] += p['adults']; e[1] += p['jacks']; e[2] += p['eggtake']
            running_season = {
                'year': yr,
                'through': newest,
                'facilities': len({p['fac'] for p in cur if p['adults'] > 0}),
                'species': sorted(([k] + v for k, v in by_sp.items()),
                                  key=lambda x: -x[1]),
            }
    envr = build_environment(A['facilities'])
    if envr:
        data['env'] = envr
    if wk and wk.get('peaks'):
        fate = build_fate(peaks, facmap)
        if fate:
            data['fate'] = fate
    A['preliminary_seasons'] = prelim_seasons
    A['final_through'] = final_through
    A.pop('_facmap', None)
    if running_season:
        data['in_season'] = running_season

    g = build_geo(data['annual']['facilities'])
    if g:
        data['geo'] = g
    if os.path.exists(paths.OUTLINE):
        # simplified Washington coastline/border for the locator map
        data['outline'] = json.load(open(paths.OUTLINE))
    manifest = json.load(open(paths.MANIFEST)) if os.path.exists(paths.MANIFEST) else {}
    fetched = sorted(v.get('fetched') or '' for v in manifest.values())
    # Every field here is derived from the data, never from the wall clock, so a run
    # that finds nothing new produces a byte-identical payload.
    data['meta'] = {
        'source': 'https://wdfw.wa.gov/fishing/management/hatcheries/escapement',
        'repo': 'https://github.com/Ethan-M2024/wdfw-hatchery-escapement',
        'seasons': sorted({r[0] for r in data['annual']['rows']}),
        'latest_fetch': (fetched[-1] if fetched else None),
        'latest_report': latest_weekly_report_date(),
        'n_annual_reports': len({r[0] for r in data['annual']['rows']}) - len(prelim_seasons),
        'preliminary_seasons': prelim_seasons,
        'final_through': final_through,
        'n_weekly_reports': (wk or {}).get('n_reports', 0),
    }
    json.dump(data, open(paths.PAYLOAD, 'w'), separators=(',', ':'))
    if prelim_seasons:
        print('preliminary seasons added from weekly reports:',
              ', '.join(f'{y}-{(y+1) % 100:02d}' for y in prelim_seasons))
    if running_season:
        print(f"in-season now: {running_season['year']}-"
              f"{(running_season['year'] + 1) % 100:02d} through {running_season['through']}")
    print('annual rows', len(data['annual']['rows']),
          '| facilities', len(data['annual']['facilities']),
          '| species', len(data['annual']['species']),
          '| geocoded', (g or {}).get('n', 0))
    if data.get('fate'):
        print('fate rows (facility x species x season):', len(data['fate']['rows']))
    if data.get('env'):
        e = data['env']
        nt = sum(1 for j in e['joins'] if j[0])
        print(f"river conditions: {len(e['rows'])} facility-seasons, "
              f"{nt} hatcheries with a temperature gauge, "
              f"PDO {len(e['ocean'].get('pdo', {}))} yrs")
    if wk:
        print('weekly series', len(wk['series']), 'from', wk['n_reports'], 'reports',
              f"({len(wk['dropped'])} mis-segmented dropped)" if wk.get('dropped') else '')
        for d in wk.get('dropped', []):
            print(f'   dropped {d[0]} {d[1]} (weekly/annual x{d[2]})')
    print('payload', os.path.getsize(paths.PAYLOAD) // 1024, 'KB')
    return data


if __name__ == '__main__':
    main()
