"""Optional pure-data progress callbacks for file-only native preparation."""
from __future__ import annotations

import time


class PreparationProgress:
    def __init__(self, callback=None, *, interval_seconds=5.0):
        self.callback = callback
        self.interval_seconds = interval_seconds
        self.started = time.monotonic()
        self.last = None

    def __call__(self, phase, completed, total, *, force=False, **details):
        if self.callback is None:
            return
        now = time.monotonic()
        if not force and self.last is not None and now - self.last < self.interval_seconds:
            return
        self.callback({'phase': phase, 'completed': completed, 'total': total,
                       'elapsed_seconds': now - self.started, **details})
        self.last = now
