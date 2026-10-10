"""Read bounded public research sources; never credentials or private networks."""
from datetime import datetime, timezone
from http.client import HTTPSConnection
from io import BytesIO
import ipaddress
import socket
import ssl
from urllib.parse import urlsplit, urljoin

from bs4 import BeautifulSoup


def public_endpoint(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
            or parsed.password or parsed.port not in (None, 443)):
        raise ValueError('Research requires a public HTTPS source')
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):
        raise ValueError('Private or non-public research endpoint rejected')
    return parsed, addresses[0][4][0]


class PinnedHTTPSConnection(HTTPSConnection):
    def __init__(self, hostname, address):
        super().__init__(hostname, timeout=12, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Pin the checked address; a second DNS answer cannot redirect the
        # request to an internal service. TLS still checks the original hostname.
        sock = socket.create_connection((self.address, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def capture_public_source(url, *, max_bytes=5 * 1024 * 1024, max_chars=20000):
    initial = url
    for _ in range(4):
        parsed, address = public_endpoint(url)
        connection = PinnedHTTPSConnection(parsed.hostname, address)
        try:
            path = parsed.path or '/'
            if parsed.query: path += '?' + parsed.query
            connection.request('GET', path, headers={'User-Agent': 'AuctionSniper/1.0 acquisition research', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location: raise ValueError('Source redirect lacks a destination')
                url = urljoin(url, location)
                continue
            if response.status != 200 or response.getheader('Content-Encoding') not in (None, '', 'identity'):
                raise ValueError('Source is not an accessible uncompressed public document')
            raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes: raise ValueError('Research source exceeds capture limit')
            content_type = response.getheader('Content-Type', '')
        finally:
            connection.close()
        title = url
        if raw.startswith(b'%PDF-'):
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(raw))
            if reader.is_encrypted or len(reader.pages) > 120:
                raise ValueError('Research PDF requires a separate document review')
            text = '\n'.join(page.extract_text() or '' for page in reader.pages)
        elif 'html' in content_type or raw.lstrip().startswith((b'<!DOCTYPE', b'<html')):
            soup = BeautifulSoup(raw, 'html.parser')
            if soup.title: title = soup.title.get_text(' ', strip=True)
            for node in soup.select('script,style,noscript,svg,nav,header,footer'):
                node.decompose()
            text = soup.get_text(' ', strip=True)
        elif content_type.startswith(('text/plain', 'application/json')):
            text = raw.decode('utf-8')
        else:
            raise ValueError('Unsupported public research content')
        if len(text.strip()) < 40: raise ValueError('No substantive source text captured')
        return {'url': url, 'requested_url': initial, 'title': title, 'text': text[:max_chars],
                'capture_truncated': len(text) > max_chars,
                'observed_at': datetime.now(timezone.utc).isoformat()}
    raise ValueError('Too many source redirects')
