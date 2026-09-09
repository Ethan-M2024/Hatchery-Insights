"""Unit tests for the two PDF parsers.

The browser test proves the finished dashboard renders; it cannot prove the numbers
on it are the numbers WDFW printed. These tests go the other way: they pin the small
decisions the parsers make about text — which line is a species heading, where a
facility name ends and a stock name begins, what "(1,234)" means — because every one
of those decisions has been wrong at least once, and each time it was wrong it moved
fish from one hatchery to another rather than failing loudly.

`lines_of` is exercised against a stub page rather than a real PDF: pdfplumber hands
it a list of word boxes, so a list of word boxes is all it needs, and the test then
runs with no fixture file to keep in sync.

Run: python3 tests/test_parse.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import parse
import parse_annual


def word(text, x0, top, x1=None):
    """One pdfplumber word box, with only the keys the parsers read."""
    return {'text': text, 'x0': x0, 'x1': x1 if x1 is not None else x0 + 8 * len(text),
            'top': top, 'bottom': top + 9}


class StubPage:
    """Stands in for a pdfplumber page: it hands back word boxes and nothing else."""

    def __init__(self, words):
        self._words = words

    def extract_words(self, **kwargs):
        # pdfplumber hands back fresh dicts each call; the parsers mutate ['text'],
        # so copies matter — a shared dict would let one test see another's edits
        return [dict(w) for w in self._words]


class Numbers(unittest.TestCase):
    """Both parsers read the same printed conventions, and must agree on them."""

    def test_plain_and_grouped(self):
        for fn in (parse.num, parse_annual.num):
            self.assertEqual(fn('0'), 0)
            self.assertEqual(fn('7'), 7)
            self.assertEqual(fn('1,234'), 1234)
            self.assertEqual(fn('1,234,567'), 1234567)

    def test_brackets_are_negative(self):
        """WDFW print a negative in brackets; read as positive it flips a shortfall
        into a surplus, which is the worst kind of wrong."""
        for fn in (parse.num, parse_annual.num):
            self.assertEqual(fn('(58)'), -58)
            self.assertEqual(fn('(1,204)'), -1204)

    def test_blank_markers_are_missing_not_zero(self):
        """A dash means the column was not reported. Zero means no fish. Folding the
        first into the second invents a count of nought and drags every average down."""
        for fn in (parse.num, parse_annual.num):
            for blank in ('-', '--'):
                self.assertIsNone(fn(blank), blank)
        self.assertIsNone(parse_annual.num('NA'))
        self.assertIsNone(parse_annual.num('N/A'))
        self.assertIsNone(parse_annual.num('n/a'))

    def test_text_is_not_a_number(self):
        for fn in (parse.num, parse_annual.num):
            self.assertIsNone(fn('COWLITZ'))
            self.assertIsNone(fn(''))

    def test_leading_and_trailing_space(self):
        self.assertEqual(parse.num('  1,020 '), 1020)
        self.assertEqual(parse_annual.num('  1,020 '), 1020)


class RunTogetherWords(unittest.TestCase):
    """Facility and stock columns touch, and pdfplumber emits one token for both."""

    def test_upper_then_title_is_split(self):
        self.assertEqual(parse.split_run_together('RINGOLD SPRINGS HATCHERYPriest'),
                         'RINGOLD SPRINGS HATCHERY Priest')
        self.assertEqual(parse.split_run_together('KALAMA FALLSKalama'),
                         'KALAMA FALLS Kalama')

    def test_ordinary_words_untouched(self):
        for text in ('COWLITZ SALMON HATCHERY', 'Priest Rapids', 'Type N Coho',
                     'Sol Duc', 'LK WHATCOM'):
            self.assertEqual(parse.split_run_together(text), text)

    def test_single_capital_is_not_a_join(self):
        """"ASummer" would be a real word split; "A Summer" would not. One capital
        before the title case is an initial, not the end of a facility name."""
        self.assertEqual(parse.split_run_together('ASummer'), 'ASummer')


class SpeciesHeadings(unittest.TestCase):
    """A species name sits at the facility column's x, one or two lines above the
    column header. Without the look-ahead it is swallowed by the row above it."""

    def test_line_above_a_column_header_is_a_heading(self):
        lines = [
            [word('COWLITZ SALMON HATCHERY', 60, 100)],
            [word('Type', 60, 130), word('N', 100, 130), word('Coho', 120, 130)],
            [word('Facility', 60, 150), word('Stock', 200, 150)],
        ]
        self.assertTrue(parse._is_species_title(lines, 1))

    def test_header_two_lines_down_still_counts(self):
        lines = [
            [word('Fall', 60, 100), word('Chinook', 90, 100)],
            [word('(preliminary)', 60, 120)],
            [word('Facility', 60, 150), word('Stock', 200, 150)],
        ]
        self.assertTrue(parse._is_species_title(lines, 0))

    def test_wrapped_row_text_is_not_a_heading(self):
        lines = [
            [word('COWLITZ', 60, 100)],
            [word('SALMON HATCHERY', 60, 112)],
            [word('GEORGE ADAMS', 60, 124)],
        ]
        self.assertFalse(parse._is_species_title(lines, 1))

    def test_end_of_page_does_not_read_past_the_last_line(self):
        lines = [[word('Fall Chinook', 60, 100)]]
        self.assertFalse(parse._is_species_title(lines, 0))

    def test_half_a_header_is_not_a_header(self):
        """"Facility" alone appears in prose on the cover page; both words together
        are what marks a table."""
        lines = [
            [word('Fall Chinook', 60, 100)],
            [word('Facility', 60, 130), word('Comments', 200, 130)],
        ]
        self.assertFalse(parse._is_species_title(lines, 0))


class Lines(unittest.TestCase):
    """Words come out of a PDF unordered; a line is rebuilt from their positions."""

    def test_words_group_by_row_and_sort_left_to_right(self):
        page = StubPage([
            word('HATCHERY', 140, 200),
            word('COWLITZ', 60, 200),
            word('GEORGE', 60, 240),
        ])
        lines = parse.lines_of(page)
        self.assertEqual([[w['text'] for w in ln] for ln in lines],
                         [['COWLITZ', 'HATCHERY'], ['GEORGE']])

    def test_a_wobbling_baseline_is_one_line(self):
        """Sub-point differences in `top` are typesetting, not new rows; left apart
        they halve a row and the numbers land on a line of their own."""
        page = StubPage([
            word('COWLITZ', 60, 200),
            word('1,204', 300, 201.6),
            word('55', 360, 200.9),
        ])
        lines = parse.lines_of(page)
        self.assertEqual(len(lines), 1)
        self.assertEqual([w['text'] for w in lines[0]], ['COWLITZ', '1,204', '55'])

    def test_clearly_separate_rows_stay_separate(self):
        page = StubPage([word('COWLITZ', 60, 200), word('GEORGE ADAMS', 60, 214)])
        self.assertEqual(len(parse.lines_of(page)), 2)

    def test_run_together_words_are_split_while_reading(self):
        page = StubPage([word('KALAMA FALLSKalama', 60, 200)])
        lines = parse.lines_of(page)
        self.assertEqual(lines[0][0]['text'], 'KALAMA FALLS Kalama')

    def test_annual_reader_groups_the_same_way(self):
        page = StubPage([
            word('Naselle', 60, 300),
            word('12,004', 300, 301.2),
            word('Grays River', 60, 330),
        ])
        lines = parse_annual.lines_of(page)
        self.assertEqual([[w['text'] for w in ln] for ln in lines],
                         [['Naselle', '12,004'], ['Grays River']])


class GlyphIds(unittest.TestCase):
    """Some annual reports carry subset fonts with no ToUnicode map, and pdfplumber
    reports raw glyph ids. Left undecoded the whole report reads as gibberish and
    silently contributes nothing."""

    def test_cids_decode_to_text(self):
        # char == cid + 29, so 38 is 'C' and 82 is 'o'
        self.assertEqual(parse_annual.decid('(cid:38)(cid:82)'), 'Co')
        self.assertEqual(parse_annual.decid('(cid:38)(cid:82)wlitz'), 'Cowlitz')

    def test_ordinary_text_passes_through_untouched(self):
        self.assertEqual(parse_annual.decid('COWLITZ SALMON'), 'COWLITZ SALMON')
        self.assertEqual(parse_annual.decid(''), '')


class ValueTokens(unittest.TestCase):
    """Which tokens the annual reader is willing to treat as a column value."""

    def test_numbers_and_blanks_are_values(self):
        for t in ('0', '12', '1,204', '(58)', 'NA', 'N/A', '-', '--'):
            self.assertTrue(parse_annual.is_val(t), t)

    def test_names_are_not_values(self):
        for t in ('Naselle', 'COWLITZ', 'Fall', ''):
            self.assertFalse(parse_annual.is_val(t), t)


class Patterns(unittest.TestCase):
    """The regexes that decide what a line is."""

    def test_data_dates_are_two_digit(self):
        self.assertTrue(parse.DATE.match('10/25/18'))
        self.assertTrue(parse.DATE.match('01/02/03'))
        self.assertFalse(parse.DATE.match('10/25/2018'))
        self.assertFalse(parse.DATE.match('1/2/18'))

    def test_footer_date_is_found_in_a_page_footer(self):
        m = parse.FOOTDATE.search('Page 2 of 9 Thursday, October 25, 2018')
        self.assertEqual(m.group(1), 'Thursday, October 25, 2018')

    def test_region_headers(self):
        self.assertTrue(parse_annual.REGION_HDR.match('PUGET SOUND REGION'))
        self.assertTrue(parse_annual.REGION_HDR.match('COLUMBIA RIVER REGION'))
        self.assertFalse(parse_annual.REGION_HDR.match('PUGET SOUND'))

    def test_total_rows_are_recognised(self):
        for t in ('TOTAL', 'Total Puget Sound', 'SUBTOTAL', 'GRAND TOTAL'):
            self.assertTrue(parse_annual.TOTAL_ROW.match(t), t)
        self.assertFalse(parse_annual.TOTAL_ROW.match('Totem Creek'))


class Columns(unittest.TestCase):
    """The two parsers write into a fixed set of columns; the rest of the pipeline
    indexes them by name, so a rename here has to break a test, not the dashboard."""

    def test_weekly_fields(self):
        self.assertEqual(parse.FIELDS[:3], ['adult_total', 'jack_total', 'eggtake'])
        self.assertEqual(len(parse.FIELDS), 11)

    def test_annual_columns_are_unique(self):
        self.assertEqual(len(parse_annual.COLS), len(set(parse_annual.COLS)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
