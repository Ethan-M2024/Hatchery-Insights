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


def norm_fac(name):
    n = re.sub(r'\s+', ' ', (name or '').strip().upper())
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
                cur = {'grp': grp, 'start': d, 'peak': total, 'wk': {}}
                runs.append(cur)
            cur['peak'] = max(cur['peak'], total)
            wk = (d - cur['start']).days // 7
            if 0 <= wk <= 60:
                cur['wk'][wk] = max(cur['wk'].get(wk, 0), total)

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
        out.append({'sp': sps.index(grp), 'season': season, 'w': series})
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
    return {'species': [sps[o] for o in used], 'series': out,
            'n_reports': len(rep_meta), 'n_files': len(seen_files),
            'dropped': dropped}


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
        'n_annual_reports': len({r[0] for r in data['annual']['rows']}),
        'n_weekly_reports': (wk or {}).get('n_reports', 0),
    }
    json.dump(data, open(paths.PAYLOAD, 'w'), separators=(',', ':'))
    print('annual rows', len(data['annual']['rows']),
          '| facilities', len(data['annual']['facilities']),
          '| species', len(data['annual']['species']),
          '| geocoded', (g or {}).get('n', 0))
    if wk:
        print('weekly series', len(wk['series']), 'from', wk['n_reports'], 'reports',
              f"({len(wk['dropped'])} mis-segmented dropped)" if wk.get('dropped') else '')
        for d in wk.get('dropped', []):
            print(f'   dropped {d[0]} {d[1]} (weekly/annual x{d[2]})')
    print('payload', os.path.getsize(paths.PAYLOAD) // 1024, 'KB')
    return data


if __name__ == '__main__':
    main()
