"""Match escapement-report facility names to the WDFW HatcheryLikeFacilities GIS layer.

The escapement PDFs use Adult-Report-Database short names ("SOOS CR"); the GIS layer
uses full facility names ("Soos Cr Hatchery"). Matching is done on a shared
normalisation, then by token containment, and anything left over is reported rather
than guessed at — an unmatched hatchery simply has no coordinates.
"""
import json, re, sys, urllib.request, urllib.parse, time
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
from paths import open_text


GIS_LAYERS = [1, 2, 3, 4, 5, 12]
BASE = ("https://geodataservices.wdfw.wa.gov/arcgis/rest/services/"
        "FP_FishMaps/HatcheryLikeFacilities/MapServer/{}/query")
FIELDS = ("FacilityName,Longitude,Latitude,FacilityType,OwnerClass,Owner,Operator,"
          "County,WRIA,ActiveYN,AdjacentWaterbody,WaterbodySystem,RegionWDFW,ElevationFT")

# facility-type words that appear on one side but not the other
TYPE_WORDS = (r'HATCHERY|HATCHRY|HATCH|PONDS?|REARING|REARIN|TRAP|FCF|SALMON|'
              r'RACK|FISH|ADULT|JUVENILE|SCREW|ACCLIMATION|ACCLIM|ACCL|NPS?|'
              r'NET ?PEN|CO-?OP|FACILITY|STATION|SPRINGS?|EGG')
TYPE_RE = re.compile(r'\b(' + TYPE_WORDS + r')\b')

ALIAS = {
    # escapement name -> GIS name, where normalisation alone cannot bridge the gap
    'COWLITZ TROUT': 'Cowlitz Trout Hatchery',
    'COWLITZ SALMON': 'Cowlitz Salmon Hatchery',
    'VOIGHT CR': 'Voights Cr Hatchery',
    'SOLDUC': 'Sol Duc Hatchery',
    'BAKER SP BEACHES 3+4': 'Baker Spawning Beach 4',
    'BAKER SPAWNING BEACHES': 'Baker Spawning Beach 3',
    'LK ABERDEEN': 'Lake Aberdeen Hatchery',
    'LK WENATCHEE NP': 'Lake Wenatchee Net Pens',
    'MAYR BROTHERS': 'Mayr Brothers Rearing Ponds',
    'NORTH TOUTLE': 'North Toutle Hatchery',
    'NF TOUTLE': 'North Toutle Hatchery',
    'PRIEST RAPIDS': 'Priest Rapids Hatchery',
    'TUMWATER FALLS': 'Tumwater Falls Hatchery',
    'GARRISON SPRING': 'Garrison Springs Hatchery',
    'GLENWOOD SPRING': 'Glenwood Springs',
    'HUPP SPRING': 'Hupp Springs Hatchery',
    'EELLS SPRING': 'Eells Springs Hatchery',
    'SATSOP SPRING': 'Satsop Springs Ponds',
    'RINGOLD SPRING': 'Ringold Springs Hatchery',
    'WALLACE R': 'Wallace River Hatchery',
    'CEDAR R': 'Cedar River Hatchery',
    'GRAYS R': 'Grays River Hatchery',
    'LEWIS R': 'Lewis River Hatchery',
    'ELOCHOMAN SILL': 'Elochoman Hatchery',
    'BARNABY SLOUGH PD': 'Barnaby Slough Ponds',
    'MERWIN DAM': 'Merwin Dam FCF',
    'WYNOOCHEE DAM': 'Wynoochee Dam Trap',
    'LOWER GRANITE DAM': 'Lower Granite Dam Trap',
    'BALLARD LOCKS': 'Hiram M Chittenden Locks',
    'CHELAN PUD': 'Chelan Falls Hatchery',
    'DAYTON ACCLIMA': 'Dayton Acclimation Pond',
    'FOSTER RD': 'Foster Road RBW',
    'BAKER LK': 'Baker Lk Hatchery',
    'BAKER SPAWNING BEACHES': 'Baker Lake Spawning Beach 1',
    'LOWER DUNGENESS R': 'Dungeness Screw Trap',
    'ONALASKA HS(ONALASK': 'Onalaska High School FFA',
    'WENATCHEE NET PENS': 'Lk Wenatchee NPs',
    'LK WENATCHEE NP': 'Lk Wenatchee NPs',
    'ELK CR': 'Elk Adult Fishway & Trap',
    'MAYR BROTHERS': 'Mayr Bros. Rearing Pond',
    'TACOMA POWER WYNOOCHEE': 'Wynoochee Dam Trap',
    'TWISP ACCLIMATION PD': 'Twisp Accl Ponds-lower',
    'WASHOUGAL R FISH WEIR': 'Washougal Intake Trap',
}
ALIAS['BAKER SP BEACHES 3+4'] = 'Baker Lake Spawning Beach 2'


def fetch_gis(path=None, refresh=False):
    path = path or paths.GIS_FACILITIES
    if os.path.exists(path) and not refresh:
        return json.load(open(path))
    seen = {}
    for lid in GIS_LAYERS:
        off = 0
        while True:
            q = urllib.parse.urlencode({'where': '1=1', 'outFields': FIELDS,
                                        'returnGeometry': 'false', 'f': 'json',
                                        'resultOffset': off, 'resultRecordCount': 1000})
            d = json.load(urllib.request.urlopen(BASE.format(lid) + '?' + q, timeout=90))
            fs = d.get('features', [])
            for f in fs:
                a = f['attributes']
                seen[(a.get('FacilityName'), a.get('Longitude'), a.get('Latitude'))] = a
            if len(fs) < 1000:
                break
            off += 1000
            time.sleep(0.2)
    recs = [v for v in seen.values() if v.get('Latitude') and v.get('Longitude')]
    json.dump(recs, open(path, 'w'))
    return recs


def norm(name):
    n = re.sub(r'\s+', ' ', (name or '').upper()).replace('.', '').replace("'", '')
    n = n.replace('&', ' AND ').replace('-', ' ')
    n = re.sub(r'\bCREEK\b', 'CR', n)
    n = re.sub(r'\bRIVER\b', 'R', n)
    n = re.sub(r'\bLAKE\b', 'LK', n)
    n = re.sub(r'\bNORTH FORK\b|\bNF\b', 'NORTH', n)
    n = TYPE_RE.sub(' ', n)
    return re.sub(r'\s+', ' ', n).strip()


def build(facilities, gis=None, verbose=False):
    gis = gis or fetch_gis()
    by_norm = {}
    by_name = {}
    for g in gis:
        by_name[g['FacilityName']] = g
        by_norm.setdefault(norm(g['FacilityName']), []).append(g)

    out, unmatched = {}, []
    for fac in facilities:
        g, how = None, None
        if fac in ALIAS and ALIAS[fac] in by_name:
            g, how = by_name[ALIAS[fac]], 'alias'
        if g is None:
            cands = by_norm.get(norm(fac))
            if cands:
                g, how = pick(cands), 'exact'
        if g is None:
            key = norm(fac)
            toks = key.split()
            if toks:
                hits = [c for k, v in by_norm.items()
                        if k.split()[:len(toks)] == toks for c in v]
                if not hits:
                    hits = [c for k, v in by_norm.items()
                            if k and (k.startswith(key + ' ') or key.startswith(k + ' '))
                            for c in v]
                names = {c['FacilityName'] for c in hits}
                if hits and len(names) <= 3:
                    g, how = pick(hits), 'token'
        if g is None:
            unmatched.append(fac)
            continue
        out[fac] = {
            'lat': round(g['Latitude'], 6), 'lon': round(g['Longitude'], 6),
            'gis_name': g['FacilityName'], 'type': g.get('FacilityType'),
            'owner_class': g.get('OwnerClass'), 'operator': g.get('Operator'),
            'county': g.get('County'), 'wria': g.get('WRIA'),
            'waterbody': g.get('AdjacentWaterbody'), 'system': g.get('WaterbodySystem'),
            'active': g.get('ActiveYN'), 'elev_ft': g.get('ElevationFT'),
            'match': how,
        }
    if verbose:
        for f in sorted(out):
            print(f'  {f:<22} -> {out[f]["gis_name"]:<38} [{out[f]["match"]}]')
        print('\nUNMATCHED (no coordinates):', unmatched)
    return out, unmatched


def pick(cands):
    """Prefer an active WDFW hatchery over a trap or an inactive record."""
    def score(c):
        s = 0
        if (c.get('ActiveYN') or '').lower().startswith('y'):
            s += 4
        if (c.get('FacilityType') or '') == 'Hatchery':
            s += 3
        if (c.get('OwnerClass') or '') == 'WDFW':
            s += 2
        return -s
    return sorted(cands, key=score)[0]


if __name__ == '__main__':
    import build_data
    facs = build_data.facility_names()
    out, un = build(facs, verbose=True)
    json.dump(out, open(paths.FACILITY_GEO, 'w'), indent=0)
    print(f'\nmatched {len(out)}/{len(facs)}  ({len(out)*100//len(facs)}%)')
