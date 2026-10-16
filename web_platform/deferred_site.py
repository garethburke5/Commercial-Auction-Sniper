"""Load property data on demand without delaying private billing endpoints."""
import logging
import os
import time
from threading import Lock


class DeferredSite:
    def __init__(self, factory):
        self.origin = (os.environ.get('PUBLIC_ORIGIN') or 'http://localhost:8000').rstrip('/')
        self.base = self.origin.split('://', 1)[-1].partition('/')[2]
        self.prefix = '/' + self.base if self.base else ''
        self._factory = factory
        self._site = None
        self._lock = Lock()

    def __getattr__(self, name):
        # A failed load is not cached: a later request may retry after recovery.
        with self._lock:
            if self._site is None:
                started = time.monotonic()
                site = self._factory()
                self._site = site
                logging.getLogger('uvicorn.error').info(
                    'Auction Geek: private catalogue loaded on demand in %.2fs',
                    time.monotonic() - started)
            site = self._site
        return getattr(site, name)

    def close(self):
        # Shutdown must never start a catalogue that no request needed.
        with self._lock:
            if self._site is not None:
                self._site.catalogue.close()
