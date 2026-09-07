import unittest
from unittest.mock import Mock, patch

from collectors import browser


class BrowserFallbackTests(unittest.TestCase):
    @patch("collectors.browser._curl_http11")
    @patch("collectors.browser._session")
    def test_curl_http11_is_used_when_requests_transport_fails(self, make_session, curl):
        session = Mock();session.get.side_effect = ConnectionError("remote disconnected");make_session.return_value = session
        curl.return_value = "<html>" + ("x" * 1200) + "</html>"
        html = browser.get_html("https://example.test/catalogue", use_browser=False)
        self.assertIn("<html>", html);curl.assert_called_once()

    @patch("collectors.browser.subprocess.run")
    def test_curl_fallback_forces_http11_and_retries(self, run):
        run.return_value = Mock(returncode=0, stdout="<html>" + ("x" * 1200) + "</html>")
        html = browser._curl_http11("https://example.test/catalogue", 30000)
        self.assertIsNotNone(html)
        argv = run.call_args.args[0]
        self.assertIn("--http1.1", argv);self.assertIn("--retry-all-errors", argv);self.assertIn("Connection: close", argv)

    @patch("collectors.browser._curl_http11_bytes")
    @patch("collectors.browser._session")
    def test_get_bytes_uses_http11_curl_before_urllib(self, make_session, curl_bytes):
        session=Mock();session.get.side_effect=ConnectionError("binary transport failed");make_session.return_value=session
        payload=b"%PDF-1.7\n"+(b"x"*1200);curl_bytes.return_value=payload
        with patch("collectors.browser.urlopen") as urlopen:
            self.assertEqual(browser.get_bytes("https://example.test/brochure.pdf"),payload)
            urlopen.assert_not_called()
        curl_bytes.assert_called_once()

    @patch("collectors.browser.subprocess.run")
    def test_binary_curl_fallback_forces_http11_and_keeps_bytes(self, run):
        payload=b"%PDF-1.7\n"+(b"z"*1200);run.return_value=Mock(returncode=0,stdout=payload)
        data=browser._curl_http11_bytes("https://example.test/brochure.pdf",30000,5_000_000)
        self.assertEqual(data,payload)
        argv=run.call_args.args[0]
        self.assertIn("--http1.1",argv);self.assertIn("application/pdf",' '.join(argv));self.assertFalse(run.call_args.kwargs["text"])

    def test_browser_transport_disables_http2(self):
        self.assertIn("--disable-http2", browser._browser_launch_args())


if __name__ == "__main__":
    unittest.main()
