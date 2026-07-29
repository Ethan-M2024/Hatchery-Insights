"""Every file location in one place, so the scripts run the same on Windows and macOS.

Large derived files (the source PDFs, the parse cache) live outside version control.
The extracted CSVs are stored gzipped, and are read and written transparently.
"""
import gzip, io, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')
DATA = os.path.join(ROOT, 'data')
DOCS = os.path.join(ROOT, 'docs')
CACHE = os.path.join(ROOT, '.cache')

PDF_DIR = os.path.join(CACHE, 'weekly_pdf')
ANNUAL_DIR = os.path.join(CACHE, 'annual_pdf')

RAW_WEEKLY = os.path.join(DATA, 'raw.csv.gz')
RAW_ANNUAL = os.path.join(DATA, 'annual_raw.csv.gz')
MANIFEST = os.path.join(DATA, 'manifest.json')
PAYLOAD = os.path.join(DATA, 'dashboard_data.json')
FACILITY_GEO = os.path.join(DATA, 'facility_geo.json')
GIS_FACILITIES = os.path.join(DATA, 'wdfw_facilities.json')
OUTLINE = os.path.join(DATA, 'wa_outline.json')
WEEKLY_CACHE = os.path.join(CACHE, 'weekly_parse_cache.json.gz')

TEMPLATE = os.path.join(SRC, 'template.html')
DASHBOARD = os.path.join(DOCS, 'index.html')
RUN_LOG = os.path.join(CACHE, 'last_run.log')


def ensure_dirs():
    for d in (DATA, DOCS, CACHE, PDF_DIR, ANNUAL_DIR):
        os.makedirs(d, exist_ok=True)


def open_text(path, mode='r', **kw):
    """Open a path for text I/O, transparently gzipping anything ending in .gz."""
    kw.setdefault('encoding', 'utf-8')
    if str(path).endswith('.gz'):
        if 'b' in mode:
            raise ValueError('use open_text for text modes only')
        if 'w' in mode:
            # mtime=0 keeps the bytes deterministic, so unchanged data does not look
            # modified to git and the weekly refresh only commits real changes
            raw = gzip.GzipFile(filename=path, mode='wb', compresslevel=9, mtime=0)
        else:
            raw = gzip.open(path, mode.replace('t', '') + 'b')
        return io.TextIOWrapper(raw, encoding=kw['encoding'],
                                newline=kw.get('newline', ''))
    if 'newline' not in kw:
        kw['newline'] = ''
    return open(path, mode, **kw)
