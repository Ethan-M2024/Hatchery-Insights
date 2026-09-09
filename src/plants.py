"""What the racks put back in the water, from WDFW's own release records.

The escapement reports end at the egg: they say how many adults came to a rack and
how many eggs were taken, and nothing about the fish that left. WDFW publish that
separately, as a release record per plant — the facility, the water, the brood year,
the species and the number of juveniles.

    https://data.wa.gov/resource/6fex-3r7d

With both halves the chain closes: adults in, eggs taken, juveniles out, and adults
back three years later. Sunset Falls traps thirty-eight thousand fish a year and
takes no eggs at all, which reads as a failure until the release column shows it is
a trap-and-haul that carries fish upstream rather than a spawning station.

Names do not match between the two records — the escapement PDFs write "LK WHATCOM"
where the release table writes "LAKE WHATCOM HATCHERY" — so they are matched on the
distinctive part of the name, and every unmatched rack is reported rather than
quietly dropped.
"""
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
import safety

RELEASES = 'https://data.wa.gov/resource/6fex-3r7d.json'
UA = 'Mozilla/5.0 (compatible; wdfw-escapement-dashboard/1.0)'
#: releases before this cannot be checked against a return in this record
FIRST_YEAR = 2000

#: words that say what a place is rather than which place it is. The escapement PDFs
#: truncate to fit a column — "RINGOLD SPRING HATC" — so a word that is merely the
#: start of one of these counts as one of them.
NOISE_WORDS = ('hatchery', 'hatchry', 'ponds', 'pond', 'rearing', 'facility', 'fcf',
               'trap', 'weir', 'creek', 'river', 'lake', 'springs', 'falls', 'dam',
               'the', 'of', 'and', 'wdfw', 'state', 'net', 'pens', 'pen', 'salmon',
               'steelhead', 'trout')
NOISE_SHORT = {'cr', 'lk', 'r', 'spr', 'sp', 'hat', 'hatc', 'htch'}

#: the reports abbreviate to fit a column, so the full name is only comparable once
#: the short forms are spelled out
EXPAND = {'lk': 'lake', 'cr': 'creek', 'r': 'river', 'spr': 'springs',
          'sp': 'springs', 'pd': 'pond', 'pds': 'pond', 'ponds': 'pond',
          'hatchry': 'hatchery', 'hatch': 'hatchery', 'hatc': 'hatchery',
          'htch': 'hatchery', 'hat': 'hatchery', 'htchy': 'hatchery',
          'fcf': 'facility', 'pens': 'pen'}

#: words that say only that a place is a fish station. Everything else — including
#: "lake", "creek" and "salmon" — tells two racks apart and is kept.
PURE_FURNITURE = {'hatchery', 'pond', 'rearing', 'facility', 'trap', 'weir', 'dam',
                  'the', 'of', 'and', 'wdfw', 'state'}


def _is_noise(word):
    if word in NOISE_SHORT:
        return True
    return any(w.startswith(word) and len(word) >= 3 for w in NOISE_WORDS)


def key_words(name):
    """The distinctive words of a rack's name, singular and lower case.

    "LK WHATCOM", "Lake Whatcom Hatchery" and "WHATCOM CR HATCHERY" are one rack;
    "COWLITZ SALMON" and "COWLITZ TROUT" are two, which is why the second word is
    kept when there is one.
    """
    text = re.sub(r'[^A-Za-z ]', ' ', str(name or '')).lower()
    words = []
    for word in text.split():
        if _is_noise(word):
            continue
        # singular, so VOIGHTS CR and VOIGHT CR are the same rack
        words.append(word[:-1] if len(word) > 4 and word.endswith('s') else word)
    return tuple(words[:2])


def key_of(name):
    return ' '.join(key_words(name))


def full_key(name):
    """Every word of a rack's name that is not pure furniture, as an unordered set.

    The distinctive-word key is deliberately blunt, and two real racks can land on
    it: Lake Whatcom Hatchery and Whatcom Creek Hatchery both reduce to "whatcom",
    as do Cowlitz Salmon and Cowlitz Trout to "cowlitz". This keeps the words that
    tell them apart, and takes them as a set because "LK WHATCOM" and "WHATCOM LK"
    are the same rack written two ways.
    """
    text = re.sub(r'[^A-Za-z ]', ' ', str(name or '')).lower()
    words = set()
    for word in text.split():
        word = EXPAND.get(word, word)
        if word in PURE_FURNITURE:
            continue
        words.add(word[:-1] if len(word) > 4 and word.endswith('s') else word)
    return frozenset(words)


def fetch(refresh=False, say=print):
    cache = os.path.join(paths.CACHE, 'fish_plants.json')
    if os.path.exists(cache) and not refresh:
        with open(cache, encoding='utf-8') as f:
            return json.load(f)
    rows, offset = [], 0
    while True:
        url = (f'{RELEASES}?$limit=50000&$offset={offset}&$order=:id'
               f'&$where=release_year>=%27{FIRST_YEAR}%27')
        page = json.loads(safety.fetch(url, timeout=180, user_agent=UA)
                          .decode('utf-8'))
        rows.extend(page)
        if len(page) < 50000:
            break
        offset += 50000
    os.makedirs(paths.CACHE, exist_ok=True)
    with open(cache, 'w', encoding='utf-8') as f:
        json.dump(rows, f)
    say(f'   fish plants: {len(rows):,} releases since {FIRST_YEAR}')
    return rows


def to_int(value):
    try:
        return int(float(str(value).replace(',', '')))
    except (TypeError, ValueError):
        return 0


def build(rows, facilities, species_names, say=print):
    """Releases per rack, species and year, keyed to the racks in the escapement data.

    Returns the table the dashboard draws and the list of racks that could not be
    matched, because a rack quietly missing from the release column looks exactly
    like a rack that released nothing.
    """
    by_key, by_first, by_squashed = defaultdict(list), defaultdict(list), defaultdict(list)
    by_full = defaultdict(list)
    for i, name in enumerate(facilities):
        by_full[full_key(name)].append(i)
        words = key_words(name)
        if not words:
            continue
        by_key[words].append(i)
        by_first[words[0]].append(i)
        # SOL DUC and SOLDUC are the same river with a space in it
        by_squashed[''.join(words)].append(i)

    counts = defaultdict(int)          # (facility index, species, year) -> fish
    matched, unmatched = set(), defaultdict(int)
    for r in rows:
        fish = to_int(r.get('number_released'))
        if fish <= 0:
            continue
        name = (r.get('facility') or '').strip()
        words = key_words(name)
        # the whole name first, because it is the only key that can tell Lake
        # Whatcom from Whatcom Creek; then the blunter keys, each of which is only
        # allowed to answer when exactly one rack does
        targets = _only(by_full.get(full_key(name)))
        if not targets:
            targets = _only(by_key.get(words))
        # two racks answering to the same key is not a match, it is a coin toss. The
        # Cowlitz salmon and trout hatcheries both reduce to ('cowlitz',) once the
        # furniture is stripped, and taking the first put every trout release on the
        # salmon rack's chart.
        if not targets and words:
            squashed = by_squashed.get(''.join(words), [])
            targets = squashed if len(squashed) == 1 else None
        if not targets and words:
            # one distinctive word is enough when only one rack answers to it: the
            # Cowlitz has two racks and needs both words, the Kalama has one
            same = by_first.get(words[0], [])
            targets = same if len(same) == 1 else None
        if not targets:
            unmatched[name] += fish
            continue
        species = _species(r.get('species'), species_names)
        year = to_int(r.get('release_year'))
        brood = to_int(r.get('brood_year')) or year
        # species index nought is Chinook: test for None, not for truth
        if species is None or year < FIRST_YEAR:
            continue
        matched.add(targets[0])
        # one rack, one species, one release year: the sum of every plant it made
        counts[(targets[0], species, year, brood)] += fish

    table = [[fac, sp, year, brood, n]
             for (fac, sp, year, brood), n in sorted(counts.items())]
    missed = sorted(unmatched.items(), key=lambda kv: -kv[1])[:12]
    say(f'   releases: {len(table):,} rack-species-years, '
        f'{len(matched)} of {len(facilities)} racks matched to a release record')
    return {
        'cols': ['fac', 'sp', 'year', 'brood', 'released'],
        'rows': table,
        'unmatched': [{'name': n, 'released': v} for n, v in missed],
        'first_year': FIRST_YEAR,
    }


def _only(targets):
    """A list of candidate racks is a match only when there is exactly one."""
    return targets if targets and len(targets) == 1 else None


def _species(name, species_names):
    """The release table's species names, mapped onto the escapement report's."""
    text = (name or '').strip().lower()
    for i, known in enumerate(species_names):
        if known.lower() == text:
            return i
    for i, known in enumerate(species_names):
        first = known.lower().split()[0]
        if first and first in text:
            return i
    return None


def load(facilities, species_names, full=False, say=print):
    return build(fetch(refresh=full, say=say), facilities, species_names, say=say)


if __name__ == '__main__':
    data = json.load(open(os.path.join(paths.DATA, 'dashboard_data.json')))
    out = load(data['annual']['facilities'], data['annual']['species'])
    print('rows:', len(out['rows']))
    print('unmatched, biggest:', out['unmatched'][:4])
