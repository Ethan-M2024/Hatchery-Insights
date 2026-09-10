"""Unit tests for the per-rack arrival curves behind "when the fish arrive".

The curve is an average of seasons, and an average is exactly the kind of number
that looks reasonable while being wrong. Every rule that decides which seasons go
into it was put there because a season that should not have counted did: a fragment
the weekly archive opened in the middle of, a run cut in two by the March boundary,
a satellite rack whose totals belong to its parent. Those rules are pinned here.

Run: python3 tests/test_timing.py
"""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import build_data as B


class DataDates(unittest.TestCase):
    """The weekly reports date each stock's count as 10/25/18."""

    def test_two_digit_years(self):
        self.assertEqual(B.as_data_date('10/25/18'), datetime.date(2018, 10, 25))
        self.assertEqual(B.as_data_date('1/2/03'), datetime.date(2003, 1, 2))

    def test_nineties_are_last_century(self):
        self.assertEqual(B.as_data_date('10/25/98'), datetime.date(1998, 10, 25))

    def test_four_digit_years(self):
        self.assertEqual(B.as_data_date('10/25/2018'), datetime.date(2018, 10, 25))

    def test_surrounding_space(self):
        self.assertEqual(B.as_data_date('  10/25/18 '), datetime.date(2018, 10, 25))

    def test_rubbish_is_none_not_a_guess(self):
        for bad in ('', None, '25/10/18 or so', 'October 25', '13/40/18'):
            self.assertIsNone(B.as_data_date(bad), bad)


class Percentiles(unittest.TestCase):
    def test_median_of_an_odd_sample(self):
        self.assertEqual(B._pct([1, 5, 9], 50), 5)

    def test_median_of_an_even_sample_interpolates(self):
        self.assertEqual(B._pct([0, 10], 50), 5)

    def test_quartiles(self):
        self.assertEqual(B._pct([0, 10, 20, 30, 40], 25), 10)
        self.assertEqual(B._pct([0, 10, 20, 30, 40], 75), 30)

    def test_order_does_not_matter(self):
        self.assertEqual(B._pct([40, 0, 20, 10, 30], 25), 10)

    def test_empty(self):
        self.assertEqual(B._pct([], 50), 0.0)


class CrossWeek(unittest.TestCase):
    """The week a season's cumulative count passed a share of its total."""

    CURVE = {10: 100, 11: 300, 12: 700, 13: 1000}

    def test_half_way(self):
        self.assertEqual(B._cross_week(self.CURVE, 1000, 50), 12)

    def test_a_quarter(self):
        self.assertEqual(B._cross_week(self.CURVE, 1000, 25), 11)

    def test_the_whole_run(self):
        self.assertEqual(B._cross_week(self.CURVE, 1000, 100), 13)

    def test_a_curve_that_starts_already_past_the_mark(self):
        self.assertEqual(B._cross_week({40: 900, 41: 1000}, 1000, 50), 40)


class FacilityCurves(unittest.TestCase):
    """build_facility_timing, driven by rows shaped like the weekly CSV."""

    SPECIES = ['Chinook', 'Chinook · Fall']

    def rows(self, spec, facility='KALAMA FALLS', species='Fall Chinook',
             stock='Kalama- H', filed='Thursday, January 02, 2014'):
        """spec is [(data_date, cumulative adults), ...] for one stock."""
        return [{'facility': facility, 'species': species, 'stock': stock,
                 'adult_total': str(n), 'data_date': d, 'report_date': filed}
                for d, n in spec]

    def season(self, year, weeks):
        """A run: (week of season, cumulative total) turned into report rows."""
        anchor = datetime.date(year, 3, 1)
        out = []
        for w, n in weeks:
            d = anchor + datetime.timedelta(days=w * 7)
            out.append((f'{d.month}/{d.day}/{d.year % 100:02d}', n))
        return out

    def ramp(self, year, start=20, n=8, top=1000):
        """A plain season: nothing, then a steady climb to `top`."""
        return self.season(year, [(start + k, round(top * (k + 1) / n))
                                  for k in range(n)])

    def _build(self, rows, annual=None):
        """Run the builder over rows written to a throwaway weekly CSV."""
        import csv
        import io
        import tempfile
        cols = ['facility', 'species', 'stock', 'adult_total', 'data_date',
                'report_date']
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
        path = tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False)
        path.write(buf.getvalue())
        path.close()
        old = B.paths.RAW_WEEKLY
        B.paths.RAW_WEEKLY = path.name
        try:
            return B.build_facility_timing(self.SPECIES, None, annual)
        finally:
            B.paths.RAW_WEEKLY = old
            os.unlink(path.name)

    def test_three_ordinary_seasons_make_a_curve(self):
        rows = []
        for y in (2015, 2016, 2017):
            rows += self.rows(self.ramp(y))
        out = self._build(rows)
        pair = [r for r in out['rows'] if out['facilities'][r['f']] == 'KALAMA FALLS']
        self.assertTrue(pair)
        r = pair[0]
        self.assertEqual(len(r['seasons']), 3)
        self.assertEqual(r['med'][0], 0)
        self.assertEqual(r['med'][-1], 100)

    def test_a_cumulative_share_never_goes_backwards(self):
        rows = []
        for y in (2015, 2016, 2017):
            rows += self.rows(self.ramp(y))
        r = self._build(rows)['rows'][0]
        self.assertEqual(r['med'], sorted(r['med']))

    def test_the_band_contains_the_line(self):
        rows = []
        for y, start in ((2015, 18), (2016, 20), (2017, 22)):
            rows += self.rows(self.ramp(y, start=start))
        r = self._build(rows)['rows'][0]
        for lo, med, hi in zip(r['lo'], r['med'], r['hi']):
            self.assertLessEqual(lo, med + 0.5)
            self.assertGreaterEqual(hi, med - 0.5)

    def test_two_seasons_are_not_an_average(self):
        rows = self.rows(self.ramp(2015)) + self.rows(self.ramp(2016))
        self.assertEqual(self._build(rows)['rows'], [])

    def test_a_thin_season_is_left_out(self):
        """Below a couple of hundred fish one late report moves the median weeks."""
        rows = self.rows(self.ramp(2015)) + self.rows(self.ramp(2016)) + \
            self.rows(self.ramp(2017, top=20))
        self.assertEqual(self._build(rows)['rows'], [])

    def test_a_run_first_seen_half_over_is_a_tail_not_an_arrival(self):
        rows = []
        for y in (2015, 2016, 2017):
            rows += self.rows(self.season(y, [(30, 600), (31, 800), (32, 900),
                                              (33, 950), (34, 980), (35, 1000)]))
        self.assertEqual(self._build(rows)['rows'], [])

    def test_two_stocks_at_one_rack_are_added_not_maxed(self):
        """Hatchery and wild fish at the same rack are different fish."""
        rows = []
        for y in (2015, 2016, 2017):
            rows += self.rows(self.ramp(y), stock='Kalama- H')
            rows += self.rows(self.ramp(y), stock='Kalama- W')
        r = self._build(rows)['rows'][0]
        self.assertEqual(max(s[2] for s in r['seasons']), 2000)

    def test_one_stock_reported_twice_is_not_counted_twice(self):
        """The same stock's season-to-date appears in every weekly report until the
        season ends; summing the rows would count the same fish thirty times."""
        rows = []
        for y in (2015, 2016, 2017):
            once = self.rows(self.ramp(y))
            rows += once + [dict(r, report_date='Thursday, January 09, 2014')
                            for r in once]
        r = self._build(rows)['rows'][0]
        self.assertEqual(max(s[2] for s in r['seasons']), 1000)

    def test_a_season_the_archive_opened_in_the_middle_of_is_dropped(self):
        """The weekly series begins when it begins; the season before it is a
        fragment whose first report carries months of arrivals in one figure."""
        rows = []
        for y in (2015, 2016, 2017):
            rows += self.rows(self.ramp(y))
        # a fourth season from before the first report there is
        rows += self.rows(self.ramp(2013))
        r = self._build(rows)['rows'][0]
        self.assertNotIn(2013, [s[0] for s in r['seasons']])

    def test_a_season_cut_in_two_by_the_march_boundary_is_dropped(self):
        """A run arriving either side of 1 March is filed as two seasons, and the
        March half reads as a run that came five months early."""
        rows = []
        for y in (2015, 2016, 2017, 2018):
            rows += self.rows(self.ramp(y, start=44))
        rows += self.rows(self.ramp(2019, start=0))
        r = self._build(rows)['rows'][0]
        self.assertNotIn(2019, [s[0] for s in r['seasons']])
        self.assertEqual(len(r['seasons']), 4)

    def test_totals_that_agree_with_the_annual_record_are_marked(self):
        rows = []
        for y in (2015, 2016, 2017):
            rows += self.rows(self.ramp(y))
        annual = {('KALAMA FALLS', 'Chinook', y): 1000 for y in (2015, 2016, 2017)}
        r = self._build(rows, annual=annual)['rows'][0]
        self.assertEqual(r['vs_annual'], 1.0)

    def test_a_satellite_rack_is_marked_not_hidden(self):
        """Speelyai counts Lewis River fish the annual books under the Lewis. The
        arrival times are still Speelyai's, so the curve stays and says so."""
        rows = []
        for y in (2015, 2016, 2017):
            rows += self.rows(self.ramp(y))
        annual = {('KALAMA FALLS', 'Chinook', y): 100 for y in (2015, 2016, 2017)}
        r = self._build(rows, annual=annual)['rows'][0]
        self.assertEqual(r['vs_annual'], 10.0)

    def test_no_annual_figure_leaves_the_question_open(self):
        rows = []
        for y in (2015, 2016, 2017):
            rows += self.rows(self.ramp(y))
        r = self._build(rows, annual={})['rows'][0]
        self.assertIsNone(r['vs_annual'])

    def test_a_run_type_and_its_species_both_get_a_curve(self):
        """"Fall Chinook" is Chinook and it is the fall run, and a reader may want
        either."""
        rows = []
        for y in (2015, 2016, 2017):
            rows += self.rows(self.ramp(y))
        out = self._build(rows)
        self.assertEqual(sorted(self.SPECIES[r['sp']] for r in out['rows']),
                         ['Chinook', 'Chinook · Fall'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
