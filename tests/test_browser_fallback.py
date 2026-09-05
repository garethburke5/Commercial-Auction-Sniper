import unittest
from unittest.mock import Mock, patch

from collectors import browser


class BrowserFallbackTests(unittest.TestCase):
    @patch("collectors.browser._curl_http11")
    @patch("collectors.browser._session")
    def test_curl_http11_is_used_when_requests_transport_fails(self, make_session, curl):
        session = Mock()
        session.get.side_effect = ConnectionError("remote disconnected")
        make_session.return_value = session
        curl.return_value = "<html>" + ("x" * 1200) + "</html>"

        html = browser.get_html("https://example.test/catalogue", use_browser=False)

        self.assertIn("<html>", html)
        curl.assert_called_once()

    @patch("collectors.browser.subprocess.run")
    def test_curl_fallback_forces_http11_and_retries(self, run):
        run.return_value = Mock(returncode=0, stdout="<html>" + ("x" * 1200) + "</html>")

        html = browser._curl_http11("https://example.test/catalogue", 30000)

        self.assertIsNotNone(html)
        argv = run.call_args.args[0]
        self.assertIn("--http1.1", argv)
        self.assertIn("--retry-all-errors", argv)


if __name__ == "__main__":
    unittest.main()
