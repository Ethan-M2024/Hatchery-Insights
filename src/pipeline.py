#!/usr/bin/env python3
"""WDFW hatchery escapement — fetch the latest reports and rebuild the dashboard.

    python src/pipeline.py             # normal update
    python src/pipeline.py --full      # ignore every cache, re-download and re-parse
    python src/pipeline.py --check     # validate what is already built, no network
    python src/pipeline.py --no-open   # do not launch a browser at the end

WDFW posts a new weekly in-season report most Thursdays and one final annual report a
year. This repository ships the already-extracted rows, so a fresh clone only has to
fetch and read the reports published since the last commit — usually one PDF.
"""
import argparse, csv, hashlib, json, os, pathlib, re, sys, time, webbrowser
import urllib.parse, urllib.request
import multiprocessing as mp
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
import safety
from paths import open_text
from safety import SecurityError

INDEX = 'https://wdfw.wa.gov/fishing/management/hatcheries/escapement'
ORIGIN = 'https://wdfw.wa.gov'
UA = 'Mozilla/5.0 (compatible; wdfw-escapement-dashboard/1.0)'

LOG = []


def say(msg, tag='  '):
    line = f'{tag} {msg}'
    LOG.append(line)
    print(line, flush=True)


def get(url, timeout=90):
    """Host-restricted, HTTPS-only, size-capped fetch. See src/safety.py."""
    return safety.fetch(url, timeout=timeout, user_agent=UA)


# ---------------------------------------------------------------- discovery
def discover():
    html = get(INDEX).decode('utf-8', 'replace')
    weekly = sorted({m for m in re.findall(
        r'href="(/sites/default/files/[^"\s]+?\.pdf)"', html, re.I)
        if '..' not in urllib.parse.unquote(m)})
    pubs = {}
    for m in re.finditer(r'href="/publications/(\d+)"[^>]*>(.*?)</a>', html, re.S):
        label = re.sub(r'<[^>]+>', '', m.group(2)).replace('&nbsp;', ' ').strip()
        season = re.match(r'(\d{4})\s*[-–]\s*(\d{4})', label)
        if season:
            pubs[m.group(1)] = f'{season.group(1)}-{season.group(2)}'
    say(f'WDFW lists {len(weekly)} weekly reports and {len(pubs)} annual reports')
    return weekly, pubs


def is_escapement_report(path):
    """Publication slots get reused: /publications/02636 also serves an unrelated
    abalone review at the plain URL. Confirm from the cover page before accepting."""
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            head = ' '.join((pg.extract_text() or '') for pg in pdf.pages[:2])
        return 'Hatchery' in head and 'Escapement' in head
    except Exception:
        return False


def annual_pdf_urls(pub):
    if not re.fullmatch(r'\d{1,8}', pub):        # publication ids are numeric only
        return
    for suffix in ('', '_0', '_1', '_2'):
        url = f'{ORIGIN}/sites/default/files/publications/{pub}/wdfw{pub}{suffix}.pdf'
        if safety.head_ok(url, user_agent=UA):
            yield url


def weekly_filename(path):
    """Map a report URL path to a flat local filename.

    The link text comes from a page we do not control, so it is reduced to a plain
    unreserved-character name; it can never contain a separator or traversal.
    """
    trimmed = path.replace('/sites/default/files/', '').strip('/')
    return safety.safe_filename(trimmed.replace('/', '__'))


def download(url, dest, manifest, key):
    # prove the destination is inside the folder we intend to write to, whatever
    # the remote page called the file
    try:
        dest = safety.resolve_within(os.path.dirname(dest), os.path.basename(dest))
    except SecurityError as e:
        say(f'blocked unsafe download path: {e}', '!!')
        return False
    try:
        blob = get(url)
    except SecurityError as e:
        say(f'blocked: {e}', '!!')
        return False
    except Exception as e:
        say(f'could not fetch {url}: {e}', '!!')
        return False
    if not blob.startswith(b'%PDF'):
        say(f'not a PDF, skipped: {url}', '!!')
        return False
    os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
    with open(dest, 'wb') as f:
        f.write(blob)
    manifest[key] = {'url': url, 'sha': hashlib.sha256(blob).hexdigest(),
                     'bytes': len(blob),
                     'fetched': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    return True


# ---------------------------------------------------------------- parse cache
def parser_fingerprint(module_file):
    """SHA-256 of a parser's source.

    The shipped rows were produced by a particular version of the parsing code. If
    that code changes, those rows are stale no matter how fresh the PDFs are — and
    if it has not changed, there is never a reason to read a PDF twice. Recording
    the fingerprint is what lets a run tell those two cases apart instead of making
    someone remember to pass --full.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), module_file)
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()[:16]


def build_info():
    if os.path.exists(paths.BUILD_INFO):
        try:
            return json.load(open(paths.BUILD_INFO))
        except Exception:
            pass
    return {}


def save_build_info(**kw):
    info = build_info()
    info.update(kw)
    json.dump(info, open(paths.BUILD_INFO, 'w'), indent=1, sort_keys=True)



def load_cache(full=False):
    """Rows already extracted, keyed by source filename.

    Prefer the on-disk cache; otherwise rebuild it from the CSV this repository
    ships, so a fresh clone never has to re-read 700 PDFs.
    """
    if full:
        return {}, 'ignored (--full)'
    if os.path.exists(paths.WEEKLY_CACHE):
        with open_text(paths.WEEKLY_CACHE) as f:
            return json.load(f), 'local cache'
    if os.path.exists(paths.RAW_WEEKLY):
        cache = {}
        with open_text(paths.RAW_WEEKLY) as f:
            for row in csv.DictReader(f):
                src = row.get('source')
                if src:
                    cache.setdefault(src, {'sha': None, 'rows': []})['rows'].append(row)
        return cache, 'rebuilt from the rows in this repository'
    return {}, 'empty'


def save_cache(cache):
    with open_text(paths.WEEKLY_CACHE, 'w') as f:
        json.dump(cache, f)


#: How many reports to read at once. Set by main(); see worker_count().
JOBS = None


def worker_count(requested=None):
    """Decide how many PDFs to read in parallel.

    Reading a report is pure CPU with no waiting, so a pool sized to every core pins
    the whole machine for the length of the run. On a laptop that is worse than
    impolite: it thermally throttles, so the run gets slower as well as making
    everything else unusable. Leave two cores for the rest of the system and cap at
    four, which is where the wall-clock gain has flattened out anyway.

    --jobs (or the WDFW_JOBS environment variable) overrides this for a build machine
    with nothing else to do.
    """
    if requested:
        return max(1, requested)
    env = os.environ.get('WDFW_JOBS', '')
    if env.isdigit() and int(env) > 0:
        return int(env)
    return max(1, min(4, (os.cpu_count() or 4) - 2))


def _weekly_job(path):
    import parse
    try:
        return os.path.basename(path), parse.parse_pdf(path)
    except Exception as e:
        return os.path.basename(path), {'__error__': f'{type(e).__name__}: {e}'}


# ---------------------------------------------------------------- stages
def fetch(cache, full=False):
    manifest = {}
    if os.path.exists(paths.MANIFEST) and not full:
        manifest = json.load(open(paths.MANIFEST))
    weekly, pubs = discover()

    wanted = []
    for path in weekly:
        name = weekly_filename(path)
        have_rows = name in cache
        have_pdf = os.path.exists(os.path.join(paths.PDF_DIR, name))
        if not full and have_rows and not have_pdf:
            continue          # already extracted; the PDF itself is disposable
        if not full and have_pdf and manifest.get('w:' + name, {}).get('sha'):
            continue
        wanted.append((path, name))

    for path, name in wanted:
        download(ORIGIN + path, os.path.join(paths.PDF_DIR, name),
                 manifest, 'w:' + name)
    listed = {weekly_filename(p) for p in weekly}
    stale = [n for n in cache if n not in listed]
    for n in stale:
        del cache[n]
    say(f'weekly: fetched {len(wanted)} new report(s)' if wanted
        else f'weekly: nothing new, all {len(weekly)} reports already extracted')
    if stale:
        say(f'weekly: dropped {len(stale)} report(s) WDFW no longer lists')

    new_annual = []
    for pub, season in sorted(pubs.items()):
        dest = os.path.join(paths.ANNUAL_DIR, f'{season}_{pub}.pdf')
        key = 'a:' + os.path.basename(dest)
        entry = manifest.get(key, {})
        if (not full and entry.get('verified') and os.path.exists(paths.RAW_ANNUAL)
                and os.path.exists(dest)):
            continue
        if not full and entry.get('verified') and os.path.exists(paths.RAW_ANNUAL):
            continue
        if not full and os.path.exists(dest) and is_escapement_report(dest):
            manifest.setdefault(key, {})['verified'] = True
            continue
        for url in annual_pdf_urls(pub):
            if not download(url, dest, manifest, key):
                continue
            if not is_escapement_report(dest):
                say(f'{os.path.basename(url)} is not an escapement report, trying next')
                manifest.pop(key, None)
                os.remove(dest)
                continue
            manifest[key]['verified'] = True
            new_annual.append(season)
            break
    say(f'annual: fetched {len(new_annual)} new report(s)' if new_annual
        else 'annual: nothing new')

    json.dump(manifest, open(paths.MANIFEST, 'w'), indent=1, sort_keys=True)
    return manifest, new_annual


def parse_weekly(cache, manifest, full=False):
    import parse
    local = sorted(f for f in os.listdir(paths.PDF_DIR) if f.lower().endswith('.pdf'))
    todo = []
    for name in local:
        p = os.path.join(paths.PDF_DIR, name)
        sha = manifest.get('w:' + name, {}).get('sha') or \
            hashlib.sha256(open(p, 'rb').read()).hexdigest()
        cached = cache.get(name)
        if full or cached is None or (cached.get('sha') or sha) != sha:
            todo.append((name, p, sha))

    if todo:
        n_jobs = JOBS or worker_count()
        say(f'reading {len(todo)} PDF(s) using {n_jobs} of '
            f'{os.cpu_count() or "?"} cores')
        shas = {n: s for n, _, s in todo}
        with mp.Pool(n_jobs, maxtasksperchild=25) as pool:
            for n, (name, rows) in enumerate(
                    pool.imap_unordered(_weekly_job, [t[1] for t in todo],
                                        chunksize=1), 1):
                if isinstance(rows, dict):
                    say(f'could not read {name}: {rows["__error__"]}', '!!')
                    continue
                cache[name] = {'sha': shas[name], 'rows': rows}
                if len(todo) > 40 and n % 50 == 0:
                    say(f'   {n}/{len(todo)}')
        save_cache(cache)

    cols = ['report_date', 'species', 'facility', 'stock'] + parse.FIELDS + \
           ['data_date', 'comments', 'source']
    n = 0
    with open_text(paths.RAW_WEEKLY, 'w') as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for key in sorted(cache):
            for r in cache[key]['rows']:
                w.writerow({c: r.get(c) for c in cols})
                n += 1
    say(f'weekly rows: {n:,} from {len(cache)} reports')


def parse_annual():
    import parse_annual as pa
    files = sorted(f for f in os.listdir(paths.ANNUAL_DIR) if f.lower().endswith('.pdf'))
    if not files:
        say('annual PDFs are not held locally; reusing the extracted rows')
        return
    args = [(os.path.join(paths.ANNUAL_DIR, f), f.split('_')[0]) for f in files]
    n_jobs = JOBS or worker_count()
    say(f'reading {len(files)} annual report(s) using {n_jobs} of '
        f'{os.cpu_count() or "?"} cores')
    with mp.Pool(n_jobs) as pool:
        res = pool.map(pa.job, args)
    rows = [x for r in res for x in r if '__err__' not in x]
    for e in [x['__err__'] for r in res for x in r if '__err__' in x]:
        say(f'annual parse error: {e}', '!!')
    cols = ['season', 'species_race', 'region', 'facility', 'stock', 'bo',
            'table', 'row_type'] + pa.COLS + ['page']
    with open_text(paths.RAW_ANNUAL, 'w') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in cols})
    say(f'annual rows: {len(rows):,} from {len(files)} reports')


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--full', action='store_true',
                    help='ignore every cache and rebuild from the PDFs')
    ap.add_argument('--check', action='store_true',
                    help='run the validation suite only, no network')
    ap.add_argument('--no-geo', action='store_true', help='skip the location refresh')
    ap.add_argument('--no-open', action='store_true', help='do not open a browser')
    ap.add_argument('--jobs', type=int, metavar='N',
                    help='how many reports to read at once '
                         '(default: leave 2 cores free, cap at 4)')
    a = ap.parse_args(argv)

    global JOBS
    JOBS = worker_count(a.jobs)

    paths.ensure_dirs()
    t0 = time.time()
    print()
    say(f'WDFW hatchery escapement — {datetime.now().astimezone():%d %b %Y, %H:%M}', '==')

    if a.check:
        import validate
        return 0 if validate.run() else 1

    cache, origin = load_cache(full=a.full)
    say(f'already extracted: {len(cache)} weekly reports ({origin})')

    info = build_info()
    wk_fp, an_fp = parser_fingerprint('parse.py'), parser_fingerprint('parse_annual.py')
    weekly_stale = info.get('weekly_parser') not in (None, wk_fp)
    annual_stale = info.get('annual_parser') not in (None, an_fp)
    if weekly_stale:
        say('the weekly parser changed since these rows were extracted — '
            're-reading every weekly report')
        cache = {}
    if annual_stale:
        say('the annual parser changed since these rows were extracted — '
            're-reading every annual report')

    manifest, new_annual = fetch(cache, full=a.full or annual_stale)
    parse_weekly(cache, manifest, full=a.full)
    if new_annual or a.full or annual_stale or not os.path.exists(paths.RAW_ANNUAL):
        parse_annual()
    else:
        say('annual: unchanged, reusing the extracted rows')
    save_build_info(weekly_parser=wk_fp, annual_parser=an_fp)

    if not a.no_geo:
        import geo, build_data
        # include facilities that only appear in the weekly reports, so preliminary
        # seasons are mapped as well as the published ones
        facs = sorted(set(build_data.facility_names())
                      | set(build_data.weekly_facility_names()))
        mapping, unmatched = geo.build(facs)
        json.dump(mapping, open(paths.FACILITY_GEO, 'w'), indent=0)
        say(f'locations: {len(mapping)}/{len(facs)} hatcheries mapped'
            + (f'; no coordinates for {unmatched}' if unmatched else ''))

    import build_data
    build_data.main()

    import validate
    healthy = validate.run()

    import assemble
    assemble.main()

    say(f'finished in {time.time() - t0:.0f}s', '==')
    with open(paths.RUN_LOG, 'w', encoding='utf-8') as f:
        f.write('\n'.join(LOG) + '\n')

    # The share card carries figures, so it is regenerated whenever they change.
    # It needs a browser, which a plain clone will not have, so a failure here is
    # reported and moved past rather than allowed to fail the run.
    try:
        import preview_card
        preview_card.main()
    except Exception as e:
        say(f'link preview not regenerated ({type(e).__name__}); '
            f'run "python src/preview_card.py" if you need it')

    if not a.no_open and healthy:
        say(f'opening {paths.DASHBOARD}', '==')
        # as_uri() percent-encodes spaces and '#', which hand-built file:/// strings
        # do not — and a clone sitting in "C:\Users\Jo Smith\Downloads" has both
        webbrowser.open(pathlib.Path(paths.DASHBOARD).resolve().as_uri())
    return 0 if healthy else 1


if __name__ == '__main__':
    mp.freeze_support()          # required by the Windows spawn start method
    sys.exit(main())
