#!/usr/bin/env python3
"""River and ocean conditions, joined to the hatcheries.

Escapement data says what came back. It cannot say why. This module adds the two
covariates that most plausibly explain the variation:

  * **River conditions** from USGS gauges — water temperature and discharge. Adult
    salmon holding at a rack in warm, low water die before they spawn; that is the
    mechanism behind the sockeye pre-spawn mortality rate this project measures.
  * **Ocean conditions** from the PDO and NPGO indices — the dominant control on
    marine survival, and so on how many fish there are to come back at all.

A gauge is only useful if it describes the water the fish are actually in, so a
match is only accepted when the gauge is close *and* the join is recorded with its
distance and station name, for the reader to judge.
"""
import bisect, collections, datetime, gzip, io, json, math, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths, safety
from paths import open_text

UA = 'Mozilla/5.0 (compatible; wdfw-escapement-dashboard/1.0)'
NWIS = 'https://waterservices.usgs.gov/nwis'
PDO_URL = 'https://www.ncei.noaa.gov/pub/data/cmb/ersst/v5/index/ersst.v5.pdo.dat'
NPGO_URL = 'https://www.o3d.org/npgo/data/NPGO.txt'

P_TEMP, P_FLOW = '00010', '00060'
MAX_GAUGE_KM = 25          # beyond this a gauge is describing different water
SEASON_START_MONTH = 3

#: adult salmonids begin to suffer above ~18 C and are in serious trouble above 20 C
THERMAL_STRESS_C = 18.0
THERMAL_SEVERE_C = 20.0


def say(msg):
    print(f'   {msg}', flush=True)


def haversine_km(lat1, lon1, lat2, lon2):
    r, p = 6371.0, math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


# ------------------------------------------------------------------ USGS
def _rdb(url):
    txt = safety.fetch(url, user_agent=UA, timeout=120).decode('utf-8', 'replace')
    lines = [l for l in txt.splitlines() if l and not l.startswith('#')]
    if len(lines) < 3:
        return []
    hdr = lines[0].split('\t')
    return [dict(zip(hdr, l.split('\t'))) for l in lines[2:]]


def gauge_catalogue(param):
    url = (f'{NWIS}/site/?format=rdb&stateCd=wa&siteType=ST&siteStatus=all'
           f'&hasDataTypeCd=dv&outputDataTypeCd=dv&parameterCd={param}')
    out = {}
    for r in _rdb(url):
        try:
            out[r['site_no']] = {'lat': float(r['dec_lat_va']),
                                 'lon': float(r['dec_long_va']),
                                 'name': r['station_nm'].strip()}
        except (KeyError, ValueError):
            continue
    return out


_TOKENS = re.compile(r'[A-Z]+')


def _shared_words(a, b):
    stop = {'RIVER', 'R', 'CREEK', 'CR', 'NEAR', 'AT', 'WA', 'FORK', 'NORTH', 'SOUTH',
            'EAST', 'WEST', 'LAKE', 'LK', 'BELOW', 'ABOVE', 'HATCHERY', 'THE', 'OF'}
    wa = {w for w in _TOKENS.findall((a or '').upper()) if len(w) > 2 and w not in stop}
    wb = {w for w in _TOKENS.findall((b or '').upper()) if len(w) > 2 and w not in stop}
    return wa & wb


def match_gauges(geo, catalogue, kind):
    """Nearest gauge, preferring one whose station name names the same water.

    Distance alone puts a hatchery on the wrong river often enough to matter — two
    basins can be ten kilometres apart over a ridge. A shared river name is much
    stronger evidence, so a named match is allowed to be further away.
    """
    joined = {}
    for fac, g in geo.items():
        lat, lon = g.get('lat'), g.get('lon')
        if lat is None:
            continue
        water = f"{g.get('waterbody') or ''} {g.get('system') or ''}"
        best = None
        for sid, s in catalogue.items():
            d = haversine_km(lat, lon, s['lat'], s['lon'])
            named = bool(_shared_words(water, s['name']))
            limit = MAX_GAUGE_KM * (2.0 if named else 1.0)
            if d > limit:
                continue
            # a named match outranks a nearer unnamed one
            score = (0 if named else 1, round(d, 2))
            if best is None or score < best[0]:
                best = (score, sid, d, s['name'], named)
        if best:
            joined[fac] = {'site': best[1], 'km': round(best[2], 1),
                           'station': best[3], 'matched_on': 'name' if best[4] else 'distance'}
    say(f'{kind}: {len(joined)}/{len(geo)} hatcheries matched to a gauge '
        f'({sum(1 for v in joined.values() if v["matched_on"] == "name")} by river name)')
    return joined


def fetch_daily(site, param, start, end):
    """Daily values for one gauge, as {date: value}."""
    url = (f'{NWIS}/dv/?format=json&sites={site}&startDT={start}&endDT={end}'
           f'&parameterCd={param}&siteStatus=all')
    try:
        blob = safety.fetch(url, user_agent=UA, timeout=180)
    except Exception as e:
        say(f'   gauge {site} {param}: {type(e).__name__}')
        return {}
    try:
        d = json.loads(blob)
    except ValueError:
        return {}
    out = {}
    for ts in d.get('value', {}).get('timeSeries', []):
        for block in ts.get('values', []):
            for v in block.get('value', []):
                try:
                    val = float(v['value'])
                except (KeyError, ValueError):
                    continue
                if val <= -999:
                    continue
                out[v['dateTime'][:10]] = val
    return out


def season_of(d):
    return d.year if d.month >= SEASON_START_MONTH else d.year - 1


def summarise_gauge(temps, flows):
    """Per-season river metrics: what a fish holding at the rack experienced."""
    by = collections.defaultdict(lambda: {'t': [], 'q': []})
    for iso, v in temps.items():
        by[season_of(datetime.date.fromisoformat(iso))]['t'].append(
            (datetime.date.fromisoformat(iso), v))
    for iso, v in flows.items():
        by[season_of(datetime.date.fromisoformat(iso))]['q'].append(
            (datetime.date.fromisoformat(iso), v))

    out = {}
    for season, rec in by.items():
        t = sorted(rec['t'])
        q = sorted(rec['q'])
        row = {}
        if len(t) >= 60:
            vals = [v for _, v in t]
            summer = [v for d, v in t if 6 <= d.month <= 9]
            roll = [sum(vals[i:i + 7]) / 7 for i in range(len(vals) - 6)] or vals
            row.update({
                't_mean_summer': round(sum(summer) / len(summer), 2) if summer else None,
                't_max7': round(max(roll), 2),
                't_days_18': sum(1 for v in vals if v >= THERMAL_STRESS_C),
                't_days_20': sum(1 for v in vals if v >= THERMAL_SEVERE_C),
                't_n': len(vals),
            })
        if len(q) >= 60:
            vals = [v for _, v in q]
            roll = [sum(vals[i:i + 7]) / 7 for i in range(len(vals) - 6)] or vals
            row.update({
                'q_mean': round(sum(vals) / len(vals), 1),
                'q_min7': round(min(roll), 1),
                'q_max': round(max(vals), 1),
                'q_n': len(vals),
            })
        if row:
            out[season] = row
    return out


# ------------------------------------------------------------------ ocean
def fetch_pdo():
    txt = safety.fetch(PDO_URL, user_agent=UA, timeout=90).decode('utf-8', 'replace')
    out = {}
    for line in txt.splitlines():
        parts = line.split()
        if len(parts) < 13 or not parts[0].isdigit():
            continue
        year = int(parts[0])
        vals = []
        for p in parts[1:13]:
            try:
                v = float(p)
            except ValueError:
                continue
            if v > -99:
                vals.append(v)
        if vals:
            out[year] = round(sum(vals) / len(vals), 3)
    return out


def fetch_npgo():
    txt = safety.fetch(NPGO_URL, user_agent=UA, timeout=90).decode('utf-8', 'replace')
    per = collections.defaultdict(list)
    for line in txt.splitlines():
        if line.strip().startswith('#'):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            per[int(float(parts[0]))].append(float(parts[2]))
        except ValueError:
            continue
    return {y: round(sum(v) / len(v), 3) for y, v in per.items() if v}


# ------------------------------------------------------------------ build
def build(refresh=False):
    if not os.path.exists(paths.FACILITY_GEO):
        say('no facility locations yet; skipping river conditions')
        return None
    geo = json.load(open(paths.FACILITY_GEO))

    cached = {}
    if os.path.exists(paths.ENVIRONMENT) and not refresh:
        with open_text(paths.ENVIRONMENT) as f:
            cached = json.load(f)

    say('cataloguing USGS gauges in Washington')
    temp_cat = gauge_catalogue(P_TEMP)
    flow_cat = gauge_catalogue(P_FLOW)
    temp_join = match_gauges(geo, temp_cat, 'water temperature')
    flow_join = match_gauges(geo, flow_cat, 'discharge')

    sites = {}
    for join, param in ((temp_join, P_TEMP), (flow_join, P_FLOW)):
        for v in join.values():
            sites.setdefault(v['site'], set()).add(param)

    start = '1998-03-01'
    end = datetime.date.today().isoformat()
    old_sites = (cached.get('gauges') or {})
    per_site = {}
    fetched = 0
    for n, (site, params) in enumerate(sorted(sites.items()), 1):
        prev = old_sites.get(site)
        if prev and not refresh and prev.get('through', '') >= end[:7]:
            per_site[site] = prev
            continue
        temps = fetch_daily(site, P_TEMP, start, end) if P_TEMP in params else {}
        flows = fetch_daily(site, P_FLOW, start, end) if P_FLOW in params else {}
        per_site[site] = {'through': end[:7],
                          'seasons': {str(k): v for k, v in
                                      summarise_gauge(temps, flows).items()}}
        fetched += 1
        if n % 25 == 0:
            say(f'   {n}/{len(sites)} gauges')
    say(f'river conditions: {fetched} gauge(s) fetched, '
        f'{len(sites) - fetched} reused from cache')

    say('fetching ocean indices')
    try:
        pdo = fetch_pdo()
    except Exception as e:
        say(f'   PDO unavailable: {type(e).__name__}')
        pdo = (cached.get('ocean') or {}).get('pdo', {})
    try:
        npgo = fetch_npgo()
    except Exception as e:
        say(f'   NPGO unavailable: {type(e).__name__}')
        npgo = (cached.get('ocean') or {}).get('npgo', {})
    say(f'ocean: PDO {len(pdo)} years, NPGO {len(npgo)} years')

    out = {
        'gauges': per_site,
        'temp_join': temp_join,
        'flow_join': flow_join,
        'ocean': {'pdo': {str(k): v for k, v in pdo.items()},
                  'npgo': {str(k): v for k, v in npgo.items()}},
        'meta': {
            'river_source': 'USGS National Water Information System (waterservices.usgs.gov)',
            'pdo_source': PDO_URL,
            'npgo_source': NPGO_URL,
            'max_gauge_km': MAX_GAUGE_KM,
            'thermal_stress_c': THERMAL_STRESS_C,
            'thermal_severe_c': THERMAL_SEVERE_C,
        },
    }
    with open_text(paths.ENVIRONMENT, 'w') as f:
        json.dump(out, f)
    return out


if __name__ == '__main__':
    build(refresh='--refresh' in sys.argv)
