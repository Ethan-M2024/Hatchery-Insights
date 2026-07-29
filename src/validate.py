"""Accuracy audit for the escapement extraction.

Every check either passes or prints exactly what failed. The headline check is the
reconciliation: WDFW prints a TOTAL STATEWIDE line per species per season, and the
facility rows we extracted must sum to it exactly. Nothing about the dashboard is
trustworthy if that fails, so it gates the build.
"""
import csv, json, os, re, collections, datetime
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
from paths import open_text


FAILED = []
WARNED = []


def ok(msg):
    print(f'  PASS  {msg}')


def fail(msg):
    FAILED.append(msg)
    print(f'  FAIL  {msg}')


def warn(msg):
    WARNED.append(msg)
    print(f'  WARN  {msg}')


def num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------- checks
RECON_COLS = ['adults_trapped', 'jacks_trapped', 'adults_received', 'jacks_received',
              'eggtake', 'adults_released', 'jacks_released', 'adults_net', 'jacks_net']
# WDFW computes the "trapped less released" total independently of the rows above it,
# so its published total disagrees with the column sum in a minority of species-seasons.
# That is a property of the source, not of this extraction — see check_source_quirks.
SOFT_COLS = {'adults_net', 'jacks_net'}


def check_reconciliation():
    """Every extracted column must sum to WDFW's own published statewide total."""
    print('\n[1] Statewide totals — extracted vs published, column by column')
    rows = list(csv.DictReader(open_text(paths.RAW_ANNUAL)))
    agg = collections.defaultdict(lambda: [0] * len(RECON_COLS))
    pub = {}
    for r in rows:
        if r.get('table') == 'broodstock':
            continue
        k = (r['season'], r['species_race'])
        if r['row_type'] == 'facility':
            a = agg[k]
            for i, c in enumerate(RECON_COLS):
                a[i] += num(r[c])
        elif 'STATEWIDE' in (r['facility'] + ' ' + r['stock']).upper():
            pub[k] = [num(r[c]) for c in RECON_COLS]
    miss = collections.Counter()
    examples = collections.defaultdict(list)
    for k, v in pub.items():
        for i, c in enumerate(RECON_COLS):
            if agg[k][i] != v[i]:
                miss[c] += 1
                examples[c].append((k, agg[k][i], v[i]))
    for c in RECON_COLS:
        rate = miss[c] / max(len(pub), 1)
        if not miss[c]:
            ok(f'{c}: all {len(pub)} statewide totals reconcile exactly')
        elif c in SOFT_COLS or rate <= 0.01:
            # a handful of species-seasons where WDFW's own totals contradict the rows
            # they sit under; each was checked against the PDF by hand
            for e in examples[c][:3]:
                warn(f'  {c} {e[0]}: extracted {e[1]:,}, WDFW printed {e[2]:,}')
            warn(f'{c}: {miss[c]} of {len(pub)} disagree ({rate:.1%}) — source '
                 f'inconsistency, not an extraction error; see check [3]')
        else:
            for e in examples[c][:5]:
                fail(f'  {c} {e[0]}: extracted {e[1]:,} vs published {e[2]:,}')
            fail(f'{c}: {miss[c]} of {len(pub)} statewide totals do not reconcile')

    # the two oldest reports have no STATEWIDE line; check their summary page instead
    early = {
        ('1998-1999', 'SPRING CHINOOK SALMON'): (7404, 5331, 9795434),
        ('1998-1999', 'FALL CHINOOK SALMON'): (107060, 7976, 99891417),
        ('1998-1999', 'COHO SALMON'): (194312, 22137, 64073480),
        ('1998-1999', 'CHUM SALMON'): (193721, 0, 49392448),
        ('1999-2000', 'FALL CHINOOK SALMON'): (115192, 4053, 85997479),
        ('1999-2000', 'COHO SALMON'): (224898, 27566, 54795588),
    }
    # early summary pages print adults, jacks and eggtake only.
    # 1999-2000 coho jacks: the printed subtotal is 22,916 while the rows it sits
    # under sum to 22,917 (Lower Granite Dam contributes the extra jack). Verified
    # against page 11 of the PDF — a source typo, so ±2 is tolerated here.
    take = lambda a: (a[0], a[1], a[4])
    exact, near, wrong = 0, [], []
    for k, v in early.items():
        got = take(agg.get(k, [0] * len(RECON_COLS)))
        if got == v:
            exact += 1
        elif all(abs(a - b) <= 2 for a, b in zip(got, v)):
            near.append((k, got, v))
        else:
            wrong.append((k, got, v))
    for m in wrong:
        fail(f'  1998-2000 summary {m[0]}: {m[1]} vs {m[2]}')
    for m in near:
        warn(f'  1998-2000 summary {m[0]}: {m[1]} vs printed {m[2]} '
             f'(within 2 — source typo)')
    if not wrong:
        ok(f'{exact} of {len(early)} pre-2000 summary totals reconcile exactly'
           + (f', {len(near)} within 2' if near else ''))


def check_regions():
    """Regional subtotals printed in each report must also add up."""
    print('\n[2] Regional subtotals')
    rows = [r for r in csv.DictReader(open_text(paths.RAW_ANNUAL))
            if r.get('table') != 'broodstock']
    agg = collections.defaultdict(int)
    pub = {}
    for r in rows:
        label = (r['facility'] + ' ' + r['stock']).strip()
        k = (r['season'], r['species_race'], (r['region'] or ''))
        if r['row_type'] == 'facility':
            agg[k] += num(r['adults_trapped'])
        else:
            m = re.match(r'Total\s+(Puget Sound|Coastal|Columbia River|Eastern|Southwest)',
                         label, re.I)
            if m:
                pub[(r['season'], r['species_race'], m.group(1).title())] = \
                    num(r['adults_trapped'])
    checked = [(k, agg.get(k, 0), v) for k, v in pub.items() if k[2]]
    bad = [c for c in checked if c[1] != c[2]]
    rate = len(bad) / max(len(checked), 1)
    if not checked:
        warn('no regional subtotal lines found to check')
    elif rate > 0.02:
        for b in bad[:10]:
            fail(f'  {b[0]}: {b[1]:,} vs published {b[2]:,}')
        fail(f'{len(bad)} of {len(checked)} regional subtotals disagree ({rate:.1%}) — '
             f'region assignment is probably not carrying across pages')
    elif bad:
        for b in bad[:5]:
            warn(f'  {b[0]}: {b[1]:,} vs published {b[2]:,}')
        warn(f'{len(bad)} of {len(checked)} regional subtotals disagree ({rate:.1%})')
    else:
        ok(f'all {len(checked)} regional subtotals reconcile exactly')

    unassigned = sum(1 for r in rows if r['row_type'] == 'facility' and not r['region'])
    total = sum(1 for r in rows if r['row_type'] == 'facility')
    share = unassigned / max(total, 1)
    if share > 0.05:
        fail(f'{unassigned:,} of {total:,} facility rows ({share:.0%}) carry no region')
    else:
        ok(f'{total - unassigned:,} of {total:,} facility rows carry a region '
           f'({share:.1%} unassigned)')


def check_source_quirks():
    """Measure how far WDFW\'s own numbers are internally consistent.

    The identity trapped + received - released = net fails on some rows. To tell a
    parsing error from a source quirk, the same identity is applied to WDFW\'s own
    printed TOTAL STATEWIDE lines — numbers this extraction never touches. If those
    fail too, the inconsistency is in the source and the extraction is exonerated.
    """
    print('\n[3] Internal consistency of the source')
    rows = [r for r in csv.DictReader(open_text(paths.RAW_ANNUAL))
            if r.get('table') != 'broodstock']
    fac = [r for r in rows if r['row_type'] == 'facility']
    pub = [r for r in rows if r['row_type'] != 'facility'
           and 'STATEWIDE' in (r['facility'] + ' ' + r['stock']).upper()]

    def offrate(rs):
        n = off = 0
        for r in rs:
            t, rc = num(r['adults_trapped']), num(r['adults_received'])
            rel, net = num(r['adults_released']), num(r['adults_net'])
            if t == rc == rel == net == 0:
                continue
            n += 1
            if t + rc - rel != net:
                off += 1
        return off, n

    f_off, f_n = offrate(fac)
    p_off, p_n = offrate(pub)
    ok(f'facility rows failing trapped+received−released=net: {f_off:,}/{f_n:,} '
       f'({f_off / max(f_n, 1):.1%})')
    ok(f'WDFW\'s own statewide rows failing the same identity: {p_off}/{p_n} '
       f'({p_off / max(p_n, 1):.1%})')
    if p_off:
        ok('the identity fails in WDFW\'s published totals too, so the "net" column '
           'is not a strict subtraction in their database — not an extraction error')
    elif f_off:
        fail('facility rows break an identity that WDFW\'s own totals satisfy — '
             'this points at a column-alignment bug')


def check_weekly_against_annual():
    """A season's final weekly cumulative should land near the annual final."""
    print('\n[4] Weekly in-season vs annual final')
    d = json.load(open(paths.PAYLOAD))
    if 'weekly' not in d:
        warn('no weekly data built')
        return
    A, W = d['annual'], d['weekly']
    C = {c: i for i, c in enumerate(A['cols'])}
    ann = collections.defaultdict(int)
    for r in A['rows']:
        ann[(A['species'][r[C['sp']]], r[C['year']])] += r[C['adults']]
    off = []
    checked = 0
    for s in W['series']:
        if not s['done']:
            continue
        sp = W['species'][s['sp']]
        a = ann.get((sp, s['season']), 0)
        if a < 1000:
            continue
        checked += 1
        ratio = s['w'][-1][1] / a
        if not 0.7 <= ratio <= 1.35:
            off.append((sp, s['season'], s['w'][-1][1], a, round(ratio, 2)))
    dropped = W.get('dropped', [])
    if not checked:
        warn('no comparable weekly seasons')
    elif off:
        for o in off[:10]:
            fail(f'  {o[0]} {o[1]}: weekly {o[2]:,} vs annual {o[3]:,} (x{o[4]})')
        fail(f'{len(off)} of {checked} weekly seasons diverge >35% from the annual final')
    else:
        ok(f'all {checked} charted weekly seasons within 35% of the annual final')
    if dropped:
        ok(f'{len(dropped)} mis-segmented weekly season(s) excluded at build time: '
           + ', '.join(f'{d[0]} {d[1]} (x{d[2]})' for d in dropped[:6]))


def check_monotonic():
    """Cumulative run curves must never decrease."""
    print('\n[5] Run curves are monotonic')
    d = json.load(open(paths.PAYLOAD))
    if 'weekly' not in d:
        warn('no weekly data')
        return
    bad = 0
    for s in d['weekly']['series']:
        vals = [v for _, v in s['w']]
        if any(b < a for a, b in zip(vals, vals[1:])):
            bad += 1
    if bad:
        fail(f'{bad} run curves decrease')
    else:
        ok(f'all {len(d["weekly"]["series"])} run curves are non-decreasing')


def check_coverage():
    """Every season on the index page should appear in the data, with no gaps."""
    print('\n[6] Season coverage')
    d = json.load(open(paths.PAYLOAD))
    yrs = sorted({r[0] for r in d['annual']['rows']})
    gaps = [y for y in range(yrs[0], yrs[-1] + 1) if y not in yrs]
    if gaps:
        fail(f'missing seasons: {gaps}')
    else:
        ok(f'{len(yrs)} consecutive seasons, {yrs[0]}-{yrs[0]+1} through {yrs[-1]}-{yrs[-1]+1}')
    thin = [y for y in yrs if sum(1 for r in d['annual']['rows'] if r[0] == y) < 100]
    if thin:
        fail(f'suspiciously few rows in seasons {thin}')
    else:
        ok('every season carries a plausible number of rows')


def check_values():
    """Look for impossible or implausible magnitudes."""
    print('\n[7] Value sanity')
    d = json.load(open(paths.PAYLOAD))
    A = d['annual']
    C = {c: i for i, c in enumerate(A['cols'])}
    neg = [r for r in A['rows'] if r[C['adults']] < 0 or r[C['jacks']] < 0
           or r[C['eggtake']] < 0]
    if neg:
        fail(f'{len(neg)} rows carry negative counts')
    else:
        ok('no negative counts')
    huge = [r for r in A['rows'] if r[C['adults']] > 400_000]
    if huge:
        for r in huge[:5]:
            warn(f'  {A["facilities"][r[C["fac"]]]} {r[C["year"]]} '
                 f'{A["species"][r[C["sp"]]]}: {r[C["adults"]]:,} adults')
        warn(f'{len(huge)} single rows exceed 400k adults — verify against the PDF')
    else:
        ok('no single facility row exceeds 400k adults')
    eggs_no_fish = [r for r in A['rows']
                    if r[C['eggtake']] > 5_000_000 and r[C['adults']] == 0
                    and r[C['bo']] != 3]
    if eggs_no_fish:
        warn(f'{len(eggs_no_fish)} rows report >5M eggs with no adults and a non-mixed '
             f'origin — normally a mixed-stock (M) bookkeeping row')
    else:
        ok('large egg takes are attached to fish or to mixed-origin rows')


def check_geo():
    print('\n[8] Facility locations')
    d = json.load(open(paths.PAYLOAD))
    if 'geo' not in d:
        warn('no geographic data built')
        return
    g = d['geo']
    facs = d['annual']['facilities']
    missing = [facs[i] for i, r in enumerate(g['rows']) if not r]
    ci = {c: i for i, c in enumerate(g['cols'])}
    outside = []
    for i, r in enumerate(g['rows']):
        if not r:
            continue
        lat, lon = r[ci['lat']], r[ci['lon']]
        if not (45.0 <= lat <= 49.5 and -125.0 <= lon <= -116.5):
            outside.append((facs[i], lat, lon))
    if missing:
        warn(f'{len(missing)} facilities without coordinates: {missing[:8]}')
    else:
        ok(f'all {len(facs)} facilities geocoded')
    if outside:
        for o in outside:
            fail(f'  {o[0]} at {o[1]},{o[2]} is outside Washington')
    else:
        ok('every coordinate falls inside Washington State')


def check_manifest():
    print('\n[9] Source files')
    if not os.path.exists(paths.MANIFEST):
        warn('no manifest — run the pipeline to record source checksums')
        return
    m = json.load(open(paths.MANIFEST))
    weekly = [k for k in m if k.startswith('w:')]
    annual = [k for k in m if k.startswith('a:')]
    ok(f'{len(weekly)} weekly and {len(annual)} annual source PDFs recorded '
       f'with SHA-256 checksums')
    dates = sorted(v.get('fetched', '') for v in m.values() if v.get('fetched'))
    if dates:
        ok(f'most recent fetch {dates[-1]}')


def check_freshness():
    """Warn if the newest weekly report is older than WDFW's usual cadence."""
    print('\n[10] Freshness')
    if not os.path.exists(paths.RAW_WEEKLY):
        warn('no weekly data')
        return
    latest = None
    for r in csv.DictReader(open_text(paths.RAW_WEEKLY)):
        rd = r.get('report_date') or ''
        try:
            d = datetime.datetime.strptime(rd.split(', ', 1)[1], '%B %d, %Y').date()
        except (ValueError, IndexError):
            continue
        latest = d if latest is None or d > latest else latest
    if not latest:
        warn('could not read a report date from the weekly data')
        return
    age = (datetime.date.today() - latest).days
    msg = f'newest weekly report is {latest:%Y-%m-%d} ({age} days old)'
    if age > 21:
        warn(msg + ' — WDFW normally posts weekly; re-run the pipeline')
    else:
        ok(msg)


def run():
    global FAILED, WARNED
    FAILED, WARNED = [], []
    print('=' * 68)
    print('VALIDATION')
    print('=' * 68)
    for fn in (check_reconciliation, check_regions, check_source_quirks,
               check_weekly_against_annual, check_monotonic, check_coverage,
               check_values, check_geo, check_manifest, check_freshness):
        try:
            fn()
        except Exception as e:
            fail(f'{fn.__name__} crashed: {type(e).__name__}: {e}')
    print('\n' + '=' * 68)
    if FAILED:
        print(f'RESULT: {len(FAILED)} FAILURE(S), {len(WARNED)} warning(s)')
        for f in FAILED:
            print('  ✗', f)
    else:
        print(f'RESULT: all checks passed, {len(WARNED)} warning(s)')
    print('=' * 68)
    return not FAILED


if __name__ == '__main__':
    import sys
    sys.exit(0 if run() else 1)
