"""Whether the fish counted here ever met an angler.

An escapement record is a count of what came back to the rack. It says nothing about
the fish taken on the way, which for a hatchery programme is half the point: a run
that produced ten thousand fish at the trap and twenty thousand in the creel is a
different programme from one that produced ten thousand and none.

The sibling project parses the creel side of the state's records, so this reads the
table it publishes rather than doing that work twice.

    https://github.com/Ethan-M2024/Creel-Insights
"""
import csv
import gzip
import io
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
import safety
import plants

CATCH = ('https://raw.githubusercontent.com/Ethan-M2024/Creel-Insights/main/'
         'data/creel_rows.csv.gz')
#: names that describe a region rather than a water, and so match everything
TOO_BROAD = {'columbia', 'puget', 'pacific', 'washington', 'sound', 'basin',
             'coastal', 'south', 'north', 'east', 'west', 'upper', 'lower'}
UA = 'Mozilla/5.0 (compatible; wdfw-escapement-dashboard/1.0)'
#: earlier than this the creel record is too thin to compare with a rack
FIRST_YEAR = 2012


def fetch(refresh=False, say=print):
    cache = os.path.join(paths.CACHE, 'creel_rows.csv.gz')
    if refresh or not os.path.exists(cache):
        blob = safety.fetch(CATCH, timeout=180, user_agent=UA)
        os.makedirs(paths.CACHE, exist_ok=True)
        with open(cache, 'wb') as f:
            f.write(blob)
    with gzip.open(cache, 'rt', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def to_int(value):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def build(rows, facilities, species_names, say=print):
    """Fish caught in each rack's own water, by species and year.

    Matched on the water rather than on the fish: a rack and a creel place are the
    same story when they share a river, and no tag in this record can say more than
    that. A rack with no creel below it simply has no row, which is the honest
    answer for a hatchery on a closed water.
    """
    by_water = defaultdict(list)
    for i, name in enumerate(facilities):
        words = plants.key_words(name)
        # "Columbia" is not a water, it is a third of the state: matching on it
        # credited a Columbia Basin rack with every coho caught between Astoria and
        # Wenatchee
        if words and words[0] not in TOO_BROAD:
            by_water[words[0]].append(i)

    caught = defaultdict(int)          # (facility, species, year) -> fish
    waters = defaultdict(set)
    for r in rows:
        year = to_int((r.get('date') or '')[:4])
        if year < FIRST_YEAR:
            continue
        # salt water belongs to no rack: the fish in a marine area came from every
        # river on the coast and from British Columbia besides
        if (r.get('water') or '') != 'fresh':
            continue
        words = plants.key_words(r.get('location'))
        if not words:
            continue
        targets = by_water.get(words[0])
        if not targets or len(targets) > 1:
            continue                    # two racks on one river cannot be told apart
        species = _species(r.get('species'), species_names)
        if species is None:
            continue
        caught[(targets[0], species, year)] += to_int(r.get('fish'))
        waters[targets[0]].add(r.get('location'))

    table = [[fac, sp, year, n] for (fac, sp, year), n in sorted(caught.items()) if n]
    say(f'   creel catch: {len(table):,} rack-species-years below {len(waters)} racks')
    return {
        'cols': ['fac', 'sp', 'year', 'caught'],
        'rows': table,
        'waters': {str(k): sorted(v)[:3] for k, v in waters.items()},
        'source': 'https://github.com/Ethan-M2024/Creel-Insights',
        'first_year': FIRST_YEAR,
    }


def _species(name, species_names):
    text = (name or '').strip().lower()
    for i, known in enumerate(species_names):
        if known.lower() == text:
            return i
    for i, known in enumerate(species_names):
        first = known.lower().split()[0]
        if first and (text == first or text.startswith(first + ' ')):
            return i
    return None


def load(facilities, species_names, full=False, say=print):
    try:
        rows = fetch(refresh=full, say=say)
    except Exception as exc:
        say(f'!! creel table unavailable: {exc}')
        return None
    return build(rows, facilities, species_names, say=say)


if __name__ == '__main__':
    data = json.load(open(os.path.join(paths.DATA, 'dashboard_data.json')))
    out = load(data['annual']['facilities'], data['annual']['species'])
    print('rows:', len(out['rows']) if out else 0)
