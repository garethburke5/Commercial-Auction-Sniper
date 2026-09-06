import unittest
from unittest.mock import patch

from collectors import browser


class BrowserUrllibFallbackTests(unittest.TestCase):
    def test_urllib_fetch_is_used_after_requests_and_curl_fail(self):
        class Response:
            status_code = 503
            text = ""
            def raise_for_status(self):
                raise RuntimeError("requests failed")

        class Session:
            def get(self, *args, **kwargs):
                return Response()

        html = "<html><body>" + ("auction catalogue " * 100) + "</body></html>"
        with patch.object(browser, "_session", return_value=Session()), \
             patch.object(browser, "_curl_http11", return_value=None), \
             patch.object(browser, "_urllib_fetch", return_value=html) as fallback:
            self.assertEqual(browser.get_html("https://example.test/catalogue"), html)
            fallback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
