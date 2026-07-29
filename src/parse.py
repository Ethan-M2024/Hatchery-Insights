import pdfplumber, re, sys, os, csv, json
from collections import defaultdict

DATE = re.compile(r'^\d{2}/\d{2}/\d{2}$')
PAGE = re.compile(r'Page \d+ of \d+')
FOOTDATE = re.compile(r'([A-Z][a-z]+day, [A-Z][a-z]+ \d{1,2}, \d{4})')
NUMTOK = re.compile(r'^[\d,]+$|^-$|^\(?-?[\d,]+\)?$')

FIELDS = ['adult_total','jack_total','eggtake','on_hand_adults','on_hand_jacks',
          'lethal_spawned','live_spawned','live_released','shipped','mortality','surplus']


def _is_species_title(lines, i):
    """True when line *i* is a species heading rather than wrapped row text.

    Each species table is introduced by its name on its own line, immediately above
    the column header. That heading sits at the same x as the facility column, so
    without this check it gets appended to the previous row's facility name — which
    is how "COWLITZ" became "COWLITZ TYPE N COHO".
    """
    for j in (i + 1, i + 2):
        if j >= len(lines):
            break
        nxt = ' '.join(w['text'] for w in lines[j])
        if 'Facility' in nxt and 'Stock' in nxt:
            return True
    return False


def lines_of(page):
    ws = page.extract_words(use_text_flow=False)
    for w in ws:
        w['text'] = split_run_together(w['text'])
    rows = defaultdict(list)
    for w in ws:
        rows[round(w['top'] / 3.0)].append(w)
    out = []
    for k in sorted(rows):
        ln = sorted(rows[k], key=lambda w: w['x0'])
        out.append(ln)
    # merge lines whose tops are within 3pt (bucketing artifacts)
    merged = []
    for ln in out:
        if merged and abs(min(w['top'] for w in ln) - min(w['top'] for w in merged[-1])) < 4:
            merged[-1] = sorted(merged[-1] + ln, key=lambda w: w['x0'])
        else:
            merged.append(ln)
    return merged


_RUN_TOGETHER = re.compile(r'([A-Z]{2,})([A-Z][a-z])')


def split_run_together(text):
    """Separate a facility name from a stock name extracted as one token.

    Long facility names sit flush against the stock column, so pdfplumber sometimes
    emits "RINGOLD SPRINGS HATCHERYPriest" as a single word. Facility names are upper
    case and stock names title case, which makes the join point recoverable.
    """
    return _RUN_TOGETHER.sub(r'\1 \2', text)


def num(t):
    t = t.strip()
    if t in ('-', '', '--'):
        return None
    neg = t.startswith('(') and t.endswith(')')
    t = t.strip('()').replace(',', '')
    try:
        v = int(t)
    except ValueError:
        try:
            v = int(float(t))
        except ValueError:
            return None
    return -v if neg else v


def parse_pdf(path):
    recs = []
    report_date = None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            species = None
            stock_x = 140.0
            lns = lines_of(page)
            for i, ln in enumerate(lns):
                txt = ' '.join(w['text'] for w in ln)
                if 'Facility' in txt and 'Stock' in txt:
                    fw = [w for w in ln if w['text'].startswith('Facility')]
                    sw = [w for w in ln if w['text'].startswith('Stock')]
                    if fw and sw:
                        stock_x = (fw[0]['x1'] + sw[0]['x0']) / 2
                    # species header is the nearest preceding non-header line
                    for j in range(i - 1, -1, -1):
                        prev = ' '.join(w['text'] for w in lns[j])
                        if ('Adult' in prev and 'Jack' in prev) or 'Hand' in prev:
                            continue
                        if 'CAUTION' in prev or 'WDFW' in prev or PAGE.search(prev):
                            break
                        if prev.strip():
                            species = prev.strip()
                        break
                    continue
                if PAGE.search(txt):
                    m = FOOTDATE.search(txt)
                    if m and not report_date:
                        report_date = m.group(1)
                    continue
                if 'CAUTION' in txt or txt.startswith('WDFW In-Season'):
                    continue
                if 'Adult' in txt and 'Jack' in txt and 'Total' in txt:
                    continue

                dates = [w for w in ln if DATE.match(w['text'])]
                if dates:
                    d = dates[-1]
                    left = [w for w in ln if w['x1'] <= d['x0'] + 1]
                    right = [w for w in ln if w['x0'] > d['x1'] - 1]
                    nums = [w for w in left if NUMTOK.match(w['text'])
                            and w['x0'] > stock_x]
                    # numeric block = last 11 numeric-ish tokens to the right of stock col
                    vals = [num(w['text']) for w in nums][-11:]
                    while len(vals) < 11:
                        vals.insert(0, None)
                    textw = [w for w in left if w not in nums]
                    fac = ' '.join(w['text'] for w in textw if w['x0'] < stock_x)
                    stk = ' '.join(w['text'] for w in textw if w['x0'] >= stock_x)
                    rec = {'species': species, 'facility': fac.strip(), 'stock': stk.strip(),
                           'data_date': d['text'],
                           'comments': ' '.join(w['text'] for w in right).strip()}
                    rec.update(dict(zip(FIELDS, vals)))
                    recs.append(rec)
                elif (recs and txt.strip()
                      and not _is_species_title(lns, i)):
                    # continuation / wrapped text
                    fac = ' '.join(w['text'] for w in ln if w['x0'] < stock_x)
                    stk = ' '.join(w['text'] for w in ln if w['x0'] >= stock_x and w['x0'] < 630)
                    cmt = ' '.join(w['text'] for w in ln if w['x0'] >= 660)
                    if fac:
                        recs[-1]['facility'] = (recs[-1]['facility'] + ' ' + fac).strip()
                    if stk:
                        recs[-1]['stock'] = (recs[-1]['stock'] + ' ' + stk).strip()
                    if cmt:
                        recs[-1]['comments'] = (recs[-1]['comments'] + ' ' + cmt).strip()
    for r in recs:
        r['report_date'] = report_date
        r['source'] = os.path.basename(path)
    return recs


if __name__ == '__main__':
    for p in sys.argv[1:]:
        rs = parse_pdf(p)
        print('==', p, len(rs), 'rows; report_date=', rs[0]['report_date'] if rs else None)
        for r in rs[:4]:
            print(json.dumps(r))
