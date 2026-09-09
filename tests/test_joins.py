"""Unit tests for the two joins that reach outside the escapement reports.

Both of these attach numbers from another record to a hatchery, and both do it on a
name, which is the least reliable key there is. A wrong join here does not crash: it
credits one hatchery with another's fish and reads perfectly plausibly on the page.
So the rules are pinned — which words are distinctive, which are furniture, and which
names are too broad to match on at all.

Run: python3 tests/test_joins.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import fishery
import plants


class KeyWords(unittest.TestCase):
    """The distinctive part of a rack's name, with the furniture stripped out."""

    def test_the_same_rack_written_three_ways(self):
        for name in ('LK WHATCOM', 'Lake Whatcom Hatchery', 'WHATCOM CR HATCHERY',
                     'Whatcom Creek Hatchery'):
            self.assertEqual(plants.key_words(name), ('whatcom',), name)

    def test_two_racks_on_one_river_keep_their_second_word(self):
        """The Cowlitz has a salmon hatchery and a trout hatchery. Reduced to
        "cowlitz" they merge, and one river's run doubles."""
        self.assertEqual(plants.key_words('COWLITZ SALMON HATCHERY'),
                         ('cowlitz',))
        self.assertEqual(plants.key_words('COWLITZ TROUT HATCHERY'),
                         ('cowlitz',))
        # ... which is why the release join also tests the squashed and unique forms
        self.assertNotEqual(plants.key_words('GEORGE ADAMS HATCHERY'),
                            plants.key_words('COWLITZ SALMON HATCHERY'))

    def test_truncated_words_still_read_as_furniture(self):
        """The weekly reports cut names to fit a column: "RINGOLD SPRING HATC"."""
        self.assertEqual(plants.key_words('RINGOLD SPRING HATC'), ('ringold',))
        # a long word loses a trailing s, so VOIGHTS and VOIGHT agree: "adams"
        # becomes "adam" on both sides of the join and still matches
        self.assertEqual(plants.key_words('GEORGE ADAMS HATCHRY'), ('george', 'adam'))

    def test_plurals_and_singulars_are_one_rack(self):
        self.assertEqual(plants.key_words('VOIGHTS CR'), plants.key_words('VOIGHT CR'))

    def test_punctuation_and_digits_are_dropped(self):
        self.assertEqual(plants.key_words('MINTER CREEK #2'), ('minter',))
        self.assertEqual(plants.key_words('Elwha (Lower)'), ('elwha', 'lower'))

    def test_at_most_two_words(self):
        self.assertEqual(len(plants.key_words('SAMISH RIVER HATCHERY WHATCOM ELWHA')), 2)

    def test_a_name_of_pure_furniture_has_no_key(self):
        """Nothing distinctive left means no match, which is the right answer: a
        blank key would match every other blank key."""
        self.assertEqual(plants.key_words('HATCHERY'), ())
        self.assertEqual(plants.key_words('THE PONDS'), ())
        self.assertEqual(plants.key_words(''), ())
        self.assertEqual(plants.key_words(None), ())

    def test_key_of_is_the_words_joined(self):
        self.assertEqual(plants.key_of('GEORGE ADAMS HATCHERY'), 'george adam')


class SpeciesLookup(unittest.TestCase):
    """The release table and the creel table each name species their own way."""

    NAMES = ['Chinook', 'Coho', 'Chum', 'Sockeye', 'Pink', 'Steelhead',
             'Rainbow', 'Cutthroat']

    def test_exact_names_match(self):
        self.assertEqual(plants._species('Chinook', self.NAMES), 0)
        self.assertEqual(plants._species('Steelhead', self.NAMES), 5)

    def test_chinook_is_index_nought_and_still_matches(self):
        """Index nought is falsy. Tested for truth instead of for None, it dropped
        every Chinook release in the record while reporting the rack as matched."""
        self.assertIsNotNone(plants._species('Chinook', self.NAMES))
        self.assertIsNotNone(fishery._species('Chinook', self.NAMES))

    def test_unknown_species_returns_none(self):
        self.assertIsNone(plants._species('Tiger Muskie', self.NAMES))
        self.assertIsNone(plants._species('', self.NAMES))
        self.assertIsNone(fishery._species('Lingcod', self.NAMES))

    def test_the_creel_reader_will_not_match_on_a_substring(self):
        """"Pink" must not swallow a species merely containing it; the creel names
        are already clean, so it only accepts the name or the name plus a qualifier."""
        self.assertIsNone(fishery._species('Pinkish Rockfish', self.NAMES))
        self.assertEqual(fishery._species('Coho Salmon', self.NAMES), 1)


class ReleaseJoin(unittest.TestCase):
    """plants.build: releases keyed to the racks the escapement record holds."""

    FACS = ['COWLITZ SALMON HATCHERY', 'COWLITZ TROUT HATCHERY', 'KALAMA FALLS',
            'SOL DUC HATCHERY']
    SP = ['Chinook', 'Coho', 'Steelhead']

    def row(self, facility, species, year, brood, n):
        return {'facility': facility, 'species': species, 'release_year': str(year),
                'brood_year': str(brood), 'number_released': str(n)}

    def test_a_plain_match(self):
        out = plants.build([self.row('Kalama Falls Hatchery', 'Coho', 2019, 2018, 5000)],
                           self.FACS, self.SP, say=lambda *a: None)
        self.assertEqual(out['rows'], [[2, 1, 2019, 2018, 5000]])
        self.assertEqual(out['unmatched'], [])

    def test_chinook_survives_the_join(self):
        out = plants.build([self.row('Kalama Falls', 'Chinook', 2019, 2018, 900)],
                           self.FACS, self.SP, say=lambda *a: None)
        self.assertEqual([r[1] for r in out['rows']], [0])

    def test_a_space_in_the_river_name_does_not_break_it(self):
        """"SOLDUC" and "SOL DUC" are the same river."""
        out = plants.build([self.row('SOLDUC HATCHERY', 'Coho', 2019, 2018, 100)],
                           self.FACS, self.SP, say=lambda *a: None)
        self.assertEqual([r[0] for r in out['rows']], [3])

    def test_an_ambiguous_river_is_not_guessed(self):
        """Two Cowlitz racks answer to "cowlitz" alone, so a release that names only
        the river is reported unmatched rather than given to one of them."""
        out = plants.build([self.row('COWLITZ HATCHERY', 'Coho', 2019, 2018, 7000)],
                           self.FACS, self.SP, say=lambda *a: None)
        self.assertEqual(out['rows'], [])
        self.assertEqual([u['name'] for u in out['unmatched']], ['COWLITZ HATCHERY'])

    def test_an_unknown_rack_is_reported_not_dropped(self):
        """A rack quietly missing looks exactly like a rack that released nothing."""
        out = plants.build([self.row('SOUTH SOUND NET PENS', 'Coho', 2019, 2018, 40000)],
                           self.FACS, self.SP, say=lambda *a: None)
        self.assertEqual(out['unmatched'],
                         [{'name': 'SOUTH SOUND NET PENS', 'released': 40000}])

    def test_plants_of_one_rack_species_and_year_are_summed(self):
        rows = [self.row('Kalama Falls', 'Coho', 2019, 2018, 1000),
                self.row('KALAMA FALLS HATCHERY', 'Coho', 2019, 2018, 500)]
        out = plants.build(rows, self.FACS, self.SP, say=lambda *a: None)
        self.assertEqual(out['rows'], [[2, 1, 2019, 2018, 1500]])

    def test_brood_years_are_kept_apart(self):
        rows = [self.row('Kalama Falls', 'Coho', 2019, 2017, 100),
                self.row('Kalama Falls', 'Coho', 2019, 2018, 200)]
        out = plants.build(rows, self.FACS, self.SP, say=lambda *a: None)
        self.assertEqual(sorted(r[3] for r in out['rows']), [2017, 2018])

    def test_a_release_before_the_first_year_is_left_out(self):
        out = plants.build([self.row('Kalama Falls', 'Coho', 1974, 1973, 100)],
                           self.FACS, self.SP, say=lambda *a: None)
        self.assertEqual(out['rows'], [])

    def test_zero_and_blank_counts_are_not_rows(self):
        rows = [self.row('Kalama Falls', 'Coho', 2019, 2018, 0),
                self.row('Kalama Falls', 'Coho', 2019, 2018, '')]
        out = plants.build(rows, self.FACS, self.SP, say=lambda *a: None)
        self.assertEqual(out['rows'], [])

    def test_a_missing_brood_year_falls_back_to_the_release_year(self):
        r = self.row('Kalama Falls', 'Coho', 2019, 2018, 100)
        r['brood_year'] = ''
        out = plants.build([r], self.FACS, self.SP, say=lambda *a: None)
        self.assertEqual(out['rows'][0][3], 2019)


class CreelJoin(unittest.TestCase):
    """fishery.build: sport catch attached to the rack on the same river."""

    FACS = ['NASELLE HATCHERY', 'COWLITZ SALMON HATCHERY', 'COWLITZ TROUT HATCHERY',
            'COLUMBIA BASIN HATCHERY']
    SP = ['Chinook', 'Coho', 'Steelhead']

    def row(self, location, species, date, fish, water='fresh'):
        return {'location': location, 'species': species, 'date': date,
                'fish': str(fish), 'water': water}

    def test_a_river_with_one_rack_on_it(self):
        out = fishery.build([self.row('Naselle River', 'Coho', '2019-09-01', 40)],
                            self.FACS, self.SP, say=lambda *a: None)
        self.assertEqual(out['rows'], [[0, 1, 2019, 40]])

    def test_salt_water_belongs_to_no_rack(self):
        """Fish in a marine area came from every river on the coast, and from British
        Columbia besides."""
        out = fishery.build(
            [self.row('Naselle River', 'Coho', '2019-09-01', 40, water='salt')],
            self.FACS, self.SP, say=lambda *a: None)
        self.assertEqual(out['rows'], [])

    def test_a_river_with_two_racks_is_left_alone(self):
        out = fishery.build([self.row('Cowlitz River', 'Coho', '2019-09-01', 900)],
                            self.FACS, self.SP, say=lambda *a: None)
        self.assertEqual(out['rows'], [])

    def test_a_region_is_not_a_water(self):
        """Matching on "Columbia" credited one Columbia Basin rack with every fish
        caught between Astoria and Wenatchee."""
        out = fishery.build([self.row('Columbia River', 'Coho', '2019-09-01', 90000)],
                            self.FACS, self.SP, say=lambda *a: None)
        self.assertEqual(out['rows'], [])

    def test_catch_is_summed_within_a_species_and_year(self):
        rows = [self.row('Naselle River', 'Coho', '2019-09-01', 10),
                self.row('Naselle R', 'Coho', '2019-10-02', 15),
                self.row('Naselle River', 'Coho', '2020-09-01', 7)]
        out = fishery.build(rows, self.FACS, self.SP, say=lambda *a: None)
        self.assertEqual(out['rows'], [[0, 1, 2019, 25], [0, 1, 2020, 7]])

    def test_early_years_are_left_out(self):
        out = fishery.build([self.row('Naselle River', 'Coho', '2001-09-01', 40)],
                            self.FACS, self.SP, say=lambda *a: None)
        self.assertEqual(out['rows'], [])

    def test_the_waters_behind_each_rack_are_recorded(self):
        """So a reader can check which river the catch was actually credited to."""
        out = fishery.build([self.row('Naselle River', 'Coho', '2019-09-01', 40)],
                            self.FACS, self.SP, say=lambda *a: None)
        self.assertEqual(out['waters'], {'0': ['Naselle River']})


if __name__ == '__main__':
    unittest.main(verbosity=2)
