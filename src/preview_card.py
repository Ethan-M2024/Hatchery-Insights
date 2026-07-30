#!/usr/bin/env python3
"""Render the link preview image that Facebook, LinkedIn and Slack show.

Those crawlers do not run JavaScript, so a share card has to be a flat image sitting
at a fixed URL. This draws one from the same payload the dashboard uses, so the
figures on the card cannot drift away from the figures on the page.

    python src/preview_card.py

Writes docs/preview.png at 1200x630, the size every platform crops to.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

W, H = 1200, 630
OUT = os.path.join(paths.DOCS, 'preview.png')

CARD = """<!doctype html><html><head><meta charset="utf-8"><style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    width:1200px; height:630px; background:#f4f6f5; color:#10201c;
    font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    padding:64px 72px; display:flex; flex-direction:column; justify-content:space-between;
  }
  .eyebrow { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:17px;
             letter-spacing:.15em; text-transform:uppercase; color:#5d6b66; }
  h1 { font-size:64px; line-height:1.04; letter-spacing:-.025em; font-weight:670;
       max-width:19ch; margin-top:22px; }
  .stats { display:flex; gap:60px; margin-top:26px; }
  .stat .n { font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
             font-size:40px; font-weight:600; letter-spacing:-.02em; }
  .stat .l { font-size:16px; color:#5d6b66; margin-top:4px; }
  .foot { display:flex; justify-content:space-between; align-items:flex-end; font-size:19px; }
  .foot .src { color:#5d6b66; }
  .foot .url { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; color:#1f6f4f; }
  .rule { height:5px; background:#1f6f4f; width:104px; margin-bottom:26px; }
</style></head><body>
  <div>
    <div class="rule"></div>
    <div class="eyebrow">Washington Dept. of Fish &amp; Wildlife</div>
    <h1>__TITLE__</h1>
    <div class="stats">__STATS__</div>
  </div>
  <div class="foot">
    <div class="src">__SRC__</div>
    <div class="url">ethan-m2024.github.io/Hatchery-Insights</div>
  </div>
</body></html>"""


def stat(n, label):
    return f'<div class="stat"><div class="n">{n}</div><div class="l">{label}</div></div>'


def build_html():
    with paths.open_text(paths.PAYLOAD) as f:
        d = json.load(f)
    meta, A = d['meta'], d['annual']
    C = {n: i for i, n in enumerate(A['cols'])}

    seasons = meta['seasons']
    # Head the card with the most recent *final* season. The season after it is
    # rebuilt from the weekly reports and still preliminary, and a share card is
    # the last place to put a figure that will move.
    latest = meta.get('final_through') or max(seasons)
    adults = sum(r[C['adults']] for r in A['rows'] if r[C['year']] == latest)
    facilities = len(A['facilities'])
    first = seasons[0]
    span = f'{first}&ndash;{str(first + 1)[2:]} to {latest}&ndash;{str(latest + 1)[2:]}'

    stats = (stat(f'{adults / 1e3:,.0f}k', f'adults trapped in {latest}&ndash;{str(latest + 1)[2:]}')
             + stat(str(facilities), 'hatcheries mapped')
             + stat(str(len(seasons)), 'seasons reconciled'))

    return (CARD
            .replace('__TITLE__', 'Every hatchery salmon counted, since 1998')
            .replace('__STATS__', stats)
            .replace('__SRC__', f'{span} &middot; parsed from WDFW reports, rebuilt daily'))


def main():
    from playwright.sync_api import sync_playwright
    html = os.path.join(paths.ROOT, '.cache', 'preview_card.html')
    os.makedirs(os.path.dirname(html), exist_ok=True)
    with open(html, 'w', encoding='utf-8') as f:
        f.write(build_html())
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={'width': W, 'height': H}, device_scale_factor=1)
        pg.goto('file://' + html)
        pg.wait_for_timeout(250)
        pg.screenshot(path=OUT)
        b.close()
    print('   preview card: %s (%d KB)' % (OUT, os.path.getsize(OUT) // 1024))


if __name__ == '__main__':
    main()
