import unittest
from unittest.mock import patch

from collectors.savills_all_future import (
    _calendar_html,
    _discover_all_future_auctions,
    _savills_property_image_from_html,
)


class SavillsAllFutureTests(unittest.TestCase):
    def test_calendar_falls_back_to_home_when_upcoming_route_fails(self):
        home = '<a href="/auctions/15--16-september-2099-242">15 & 16 September 2099</a>'
        calls=[]
        def fake_get_html(url, use_browser=False, timeout_ms=30000):
            calls.append(url)
            if url.endswith('/upcoming-auctions'):
                raise TimeoutError('transient route failure')
            if url.rstrip('/') == 'https://auctions.savills.co.uk':
                return home
            raise AssertionError(url)
        with patch('collectors.savills_all_future.get_html', side_effect=fake_get_html):
            self.assertEqual(_calendar_html(), home)
        self.assertEqual(calls[:2], [
            'https://auctions.savills.co.uk/upcoming-auctions',
            'https://auctions.savills.co.uk/',
        ])

    def test_discovers_every_future_catalogue_and_excludes_history(self):
        html = """
        <html><body>
          <section><h2>15 &amp; 16 September 2099</h2>
            <a href="/auctions/september-2099-123">View catalogue</a>
          </section>
          <section><h2>29 &amp; 30 September 2099</h2>
            <a href="https://auctions.savills.co.uk/auctions/late-september-2099-124?x=1">Preliminary lots</a>
          </section>
          <section><h2>20 October 2099</h2>
            <a href="/auctions/october-2099-125/">View catalogue</a>
          </section>
          <section><h2>3 November 2020</h2>
            <a href="/auctions/november-2020-99">Historic catalogue</a>
          </section>
        </body></html>
        """
        auctions = _discover_all_future_auctions(html)
        self.assertEqual(len(auctions), 3)
        self.assertEqual(
            [a["start"].isoformat() for a in auctions],
            ["2099-09-15", "2099-09-29", "2099-10-20"],
        )
        self.assertTrue(all("?" not in a["catalogue"] for a in auctions))

    def test_deduplicates_repeated_links_to_same_catalogue(self):
        html = """
        <html><body><section><h2>8 December 2099</h2>
          <a href="/auctions/december-2099-200">Catalogue</a>
          <a href="/auctions/december-2099-200?view=lots">Lots</a>
        </section></body></html>
        """
        auctions = _discover_all_future_auctions(html)
        self.assertEqual(len(auctions), 1)
        self.assertEqual(auctions[0]["start"].isoformat(), "2099-12-08")

    def test_extracts_root_relative_catalogue_lot_image(self):
        html = '<img alt="Lot image" src="/assets/images/lots/25025/1.jpg?width=640">'
        image = _savills_property_image_from_html(
            html,
            "https://auctions.savills.co.uk/auctions/15-september-2099-242/page-1",
        )
        self.assertEqual(
            image,
            "https://resize.auctions.savills.co.uk/assets/images/lots/25025/1.jpg?width=640",
        )

    def test_extracts_current_script_hydrated_lot_image(self):
        html = r'''<script>window.gallery=["/images\/lots\/243\/24521\/8e6ca5291d18cedb3997f735535caa71.jpeg"];</script>'''
        image = _savills_property_image_from_html(
            html,
            "https://auctions.savills.co.uk/auctions/29-september-2099-243/116-high-street-24521",
        )
        self.assertEqual(
            image,
            "https://auctions.savills.co.uk/images/lots/243/24521/8e6ca5291d18cedb3997f735535caa71.jpeg",
        )

    def test_extracts_extensionless_lot_image_route(self):
        html = '<img alt="Property" data-src="/lot-image/25025/1?width=640&height=480">'
        image = _savills_property_image_from_html(
            html,
            "https://auctions.savills.co.uk/auctions/15-september-2099-242/page-1",
        )
        self.assertEqual(
            image,
            "https://auctions.savills.co.uk/lot-image/25025/1?width=640&height=480",
        )

    def test_rejects_branding_as_property_image(self):
        html = '<img alt="Savills" src="/assets/images/savills-logo.svg">'
        self.assertIsNone(
            _savills_property_image_from_html(
                html,
                "https://auctions.savills.co.uk/auctions/15-september-2099-242/page-1",
            )
        )


if __name__ == "__main__":
    unittest.main()
