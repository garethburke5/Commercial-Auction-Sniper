"""Anonymous, bounded share telemetry using the existing application log service.

No property URLs, recipients, IPs, accounts or cookies enter these events. Logs
are the retained event stream; the owner summary covers this worker's lifetime.
"""
from collections import Counter
from datetime import datetime, timezone
from threading import Lock
import logging
import time
from typing import Literal
from pydantic import BaseModel, ConfigDict
from fastapi import HTTPException


class ShareEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    channel: Literal['menu','native','whatsapp','email','linkedin','facebook','copy']
    action: Literal['opened','selected','handed_off','copied','manual_copy']
    placement: Literal['property','card','snapshot']


class ShareMetrics:
    def __init__(self):
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.counts = Counter()
        self.lock = Lock()
        self.window = 0
        self.accepted = 0

    def record(self, event):
        allowed = {'menu': {'opened'}, 'native': {'handed_off'},
                   'copy': {'copied','manual_copy'}}
        if event.action not in allowed.get(event.channel, {'selected'}):
            raise HTTPException(422, 'Invalid share interaction')
        with self.lock:
            minute = int(time.monotonic() // 60)
            if minute != self.window:
                self.window, self.accepted = minute, 0
            if self.accepted >= 600:
                raise HTTPException(429, 'Share telemetry busy')
            self.accepted += 1
            self.counts[(event.channel,event.action,event.placement)] += 1
        logging.getLogger('uvicorn.error').info(
            'share_interaction channel=%s action=%s placement=%s count=1',
            event.channel,event.action,event.placement)

    def summary(self):
        with self.lock:
            return {'since': self.started_at, 'scope': 'current_api_worker',
                    'measurement': 'button interactions, not delivered shares or forwards',
                    'counts': [{'channel': c, 'action': a, 'placement': p, 'count': n}
                               for (c,a,p),n in sorted(self.counts.items())]}
