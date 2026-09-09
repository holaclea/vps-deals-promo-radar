"""Synthetic fixtures for parser/safety tests only; never published as offers."""
import unittest
from datetime import datetime, timezone
from scraper import parse, refresh, price
from build import classify, https, e

P = {"id":"buyvm", "adapter":"buyvm", "kind":"regular", "source_url":"https://buyvm.net/kvm-dedicated-server-slices/"}
NOW = "2026-09-09T10:00:00+00:00"
HTML = '<div class="plan fourplan"><h2>SLICE <span>512</span></h2><ul><li>512 MB Memory</li><li><strong>$24.00</strong> per year</li></ul></div><table><tr><td>Competitor $900 / month</td></tr></table>'

class SafetyTests(unittest.TestCase):
    def test_price_cycle_is_not_guessed(self):
        self.assertEqual(price('$24.00 per year'), ('24.00','year'))
        self.assertEqual(price('$4/mo ($0.006/hr)'), ('4','month'))
        with self.assertRaises(ValueError): price('$4')
    def test_scoped_plan_does_not_capture_competitor(self):
        found = parse(P, HTML, NOW, 'digest')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['price'], '24.00')
        self.assertIsNone(found[0]['valid_from'])
    def test_parse_break_preserves_old_timestamp_and_marks_stale(self):
        old = {"offers":parse(P, HTML, NOW, 'digest')}
        new = refresh({"providers":[P]}, old, '2026-09-10T10:00:00+00:00', loader=lambda _:('<h1>Changed</h1>',b'changed'), robots=lambda _:True)
        self.assertEqual(new['offers'][0]['status'], 'stale')
        self.assertEqual(new['offers'][0]['checked_at'], NOW)
        self.assertEqual(new['sources'][0]['status'], 'error')
    def test_failed_first_fetch_does_not_invent_offer(self):
        new = refresh({"providers":[P]}, {}, NOW, loader=lambda _:('',b''), robots=lambda _:True)
        self.assertEqual(new['offers'], [])
    def test_removed_offer_is_not_kept_active(self):
        old_html = HTML + HTML.replace('512','1024')
        old = {"offers":parse(P, old_html, NOW, 'digest')}
        new = refresh({"providers":[P]}, old, NOW, loader=lambda _:(HTML,HTML.encode()), robots=lambda _:True)
        self.assertEqual(len(new['offers']), 1)
    def test_robots_denial_does_not_fetch(self):
        def forbidden(_): raise AssertionError('should not fetch')
        new = refresh({"providers":[P]}, {}, NOW, loader=forbidden, robots=lambda _:False)
        self.assertIn('robots.txt',new['sources'][0]['error'])
    def test_age_out_and_expiration(self):
        offer = parse(P,HTML,NOW,'digest')[0]
        future = datetime(2026,9,13,tzinfo=timezone.utc)
        self.assertEqual(classify(offer,future,72),'stale')
        offer['valid_until'] = '2026-09-10T00:00:00+00:00'
        self.assertEqual(classify(offer,future,72),'expired')
    def test_unsafe_external_content(self):
        self.assertEqual(e('<script>'), '&lt;script&gt;')
        for url in ['javascript:alert(1)','http://example.com','https://user:secret@example.com']:
            with self.assertRaises(ValueError): https(url)

if __name__ == '__main__': unittest.main()
