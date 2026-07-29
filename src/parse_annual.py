"""Parse WDFW annual Final Hatchery Escapement Reports (1998-99 .. 2024-25).

Three layout eras, unified into one schema:
  adults_trapped, jacks_trapped, adults_received, jacks_received,
  eggtake, eggtake_goal, adults_released, jacks_released, adults_net, jacks_net
Eras A (1998-2000) and B (2000s) lack the "Total Received" pair -> filled with 0.
"""
import pdfplumber, re, os, sys, csv, json
from collections import defaultdict

NUM = re.compile(r'^\(?-?[\d,]+\)?$')
NA = re.compile(r'^(NA|N/A|-{1,2})$', re.I)
PAGEFOOT = re.compile(r'Page \d+\b', re.I)
REGION = re.compile(r'^(Total\s+)?(Puget Sound|Coastal|Columbia River|Eastern|Southwest|Statewide|Grand)\b.*Region?', re.I)
REGION_HDR = re.compile(r'^(PUGET SOUND|COASTAL|COLUMBIA RIVER|EASTERN|SOUTHWEST)\s*REGION$', re.I)
TOTAL_ROW = re.compile(r'^(TOTAL|Total|SUBTOTAL|Subtotal|GRAND)\b')

COLS = ['adults_trapped', 'jacks_trapped', 'adults_received', 'jacks_received',
        'eggtake', 'eggtake_goal', 'adults_released', 'jacks_released',
        'adults_net', 'jacks_net']


CID = re.compile(r'\(cid:(\d+)\)')


def decid(s):
    """Some reports embed subset fonts with no ToUnicode map; pdfplumber emits
    (cid:N) glyph ids. For these files char == cid + 29."""
    if '(cid:' not in s:
        return s
    return CID.sub(lambda m: chr(int(m.group(1)) + 29), s)


def lines_of(page):
    ws = page.extract_words()
    for w in ws:
        w['text'] = decid(w['text'])
    buckets = defaultdict(list)
    for w in ws:
        buckets[round(w['top'] / 3.0)].append(w)
    out = []
    for k in sorted(buckets):
        ln = sorted(buckets[k], key=lambda w: w['x0'])
        if out and abs(min(w['top'] for w in ln) - min(w['top'] for w in out[-1])) < 4.5:
            out[-1] = sorted(out[-1] + ln, key=lambda w: w['x0'])
        else:
            out.append(ln)
    return out


def num(t):
    if NA.match(t):
        return None
    t = t.strip()
    neg = t.startswith('(') and t.endswith(')')
    t = t.strip('()').replace(',', '')
    if not re.fullmatch(r'-?\d+', t):
        return None
    v = int(t)
    return -v if neg else v


def is_val(t):
    return bool(NUM.match(t) or NA.match(t))


def parse_pdf(path, season):
    rows = []
    # A region header ("Coastal Region") is printed once and then every following
    # page of that block continues it, so region has to survive the page loop and
    # reset only when the species table changes.
    region = None
    last_species = None
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            lns = lines_of(page)
            hdr_i = None
            for i, ln in enumerate(lns):
                t = ' '.join(w['text'] for w in ln)
                if re.search(r'\b(Facility|Hatchery)\b', t) and 'Adults' in t and 'Eggtake' in t:
                    hdr_i = i
                    break
            if hdr_i is None:
                continue

            hdr = lns[hdr_i]
            hdr_txt = ' '.join(w['text'] for w in hdr)
            group_txt = ' '.join(w['text'] for w in lns[hdr_i - 1]) if hdr_i else ''
            # Column set varies by era and species: chum/pink/sockeye tables carry no
            # Jacks column, only reports from ~2010 on have the "Total Received" pair,
            # and broodstock tables have one fewer adults/jacks block than escapement.
            b = 2 if 'Jacks' in hdr_txt else 1
            n_blocks = sum(1 for w in hdr if w['text'] == 'Adults')
            if n_blocks < 2:
                continue
            n_numeric = n_blocks * b + 2
            kind = 'broodstock' if (n_blocks == 2 or 'Broodstock' in group_txt) else 'escapement'

            fac_w = next((w for w in hdr if w['text'] in ('Facility', 'Hatchery')), None)
            stk_w = next((w for w in hdr if w['text'].startswith('Stock')), None)
            bo_w = next((w for w in hdr if w['text'] == 'Bo'), None)
            if not (fac_w and stk_w):
                continue
            stock_x = (fac_w['x1'] + stk_w['x0']) / 2
            bo_x = bo_w['x0'] - 4 if bo_w else None
            # first numeric column's left edge — text left of it belongs to name fields
            data_x = min((w['x0'] for w in hdr if w['text'] in ('Adults', 'Jacks')), default=1e9) - 12

            # species: title text on the group line / header line left of first group label,
            # else the nearest preceding standalone line
            species = None
            for j in (hdr_i - 1, hdr_i - 2, hdr_i - 3):
                if j < 0:
                    break
                cand = [w['text'] for w in lns[j] if w['x0'] < data_x]
                if cand and not PAGEFOOT.search(' '.join(cand)):
                    s = ' '.join(cand).strip()
                    if s and not re.match(r'^(Total|Facility|Hatchery|Stock)', s):
                        # continuation pages repeat the title as "... Cont." — same species
                        species = re.sub(r'\s*cont\s*\.?$', '', s, flags=re.I).strip()
                        break
            if species != last_species:
                region = None
                last_species = species

            for ln in lns[hdr_i + 1:]:
                txt = ' '.join(w['text'] for w in ln)
                if PAGEFOOT.search(txt) or not txt.strip():
                    continue
                if REGION_HDR.match(txt.strip()) or re.fullmatch(
                        r'(Puget Sound|Coastal|Columbia River|Eastern|Southwest)\s+Region', txt.strip(), re.I):
                    region = txt.strip().title().replace(' Region', '')
                    continue

                vals_w = [w for w in ln if is_val(w['text']) and w['x0'] >= data_x]
                if len(vals_w) < n_numeric:
                    continue
                vals_w = vals_w[-n_numeric:]
                raw = [num(w['text']) for w in vals_w]
                # Header order is: trapped [, received], the eggtake pair, released
                # [, net] — so the eggtake pair sits in the middle, not at the end.
                pre = 2 if n_blocks == 4 else 1
                flat = raw[:pre * b]
                egg = raw[pre * b:pre * b + 2]
                rest = raw[pre * b + 2:]
                pad = [0] * b

                def blkat(seq, k):
                    s = seq[k * b:(k + 1) * b]
                    return s + [0] * (b - len(s))
                trapped = blkat(flat, 0)
                received = blkat(flat, 1) if n_blocks == 4 else pad
                released = blkat(rest, 0)
                net = blkat(rest, 1) if len(rest) >= 2 * b else pad
                if b == 1:  # no jacks column for this species
                    trapped, received, released, net = (
                        [x[0], 0] for x in (trapped, received, released, net))
                vals = trapped + received + egg + released + net

                name_w = [w for w in ln if w['x0'] < vals_w[0]['x0']]
                fac = ' '.join(w['text'] for w in name_w if w['x0'] < stock_x).strip()
                if bo_x:
                    stk = ' '.join(w['text'] for w in name_w
                                   if stock_x <= w['x0'] < bo_x).strip()
                    bo = ' '.join(w['text'] for w in name_w if w['x0'] >= bo_x).strip()
                else:
                    stk = ' '.join(w['text'] for w in name_w if w['x0'] >= stock_x).strip()
                    bo = ''
                label = (fac + ' ' + stk).strip()
                if not label:
                    continue
                rec = {'season': season, 'species_race': species, 'region': region,
                       'facility': fac, 'stock': stk, 'bo': bo, 'table': kind,
                       'row_type': 'total' if TOTAL_ROW.match(label) else 'facility',
                       'page': pno}
                rec.update(dict(zip(COLS, vals)))
                rows.append(rec)
    return rows


def job(a):
    path, season = a
    try:
        return parse_pdf(path, season)
    except Exception as e:
        return [{'__err__': f'{path}: {type(e).__name__} {e}'}]


if __name__ == '__main__':
    import multiprocessing as mp
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import paths
    files = sorted(os.listdir(paths.ANNUAL_DIR))
    args = [(os.path.join(paths.ANNUAL_DIR, f), f.split('_')[0])
            for f in files if f.endswith('.pdf')]
    if len(sys.argv) > 1:
        args = [a for a in args if any(s in a[0] for s in sys.argv[1:])]
    with mp.Pool(6) as pool:
        res = pool.map(job, args)
    rows, errs = [], []
    for r in res:
        for x in r:
            (errs if '__err__' in x else rows).append(x)
    cols = ['season', 'species_race', 'region', 'facility', 'stock', 'bo',
            'table', 'row_type'] + COLS + ['page']
    with paths.open_text(paths.RAW_ANNUAL, 'w') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in cols})
    print('rows', len(rows), 'errors', len(errs))
    for e in errs[:10]:
        print(e)
