"""Per-user limits on /ask: N per minute and M per day, sliding windows, in memory.

One API process serves the demo, so in-memory is enough; a restart resets the windows.
Users pick a name without a password, so this guards the free-tier LLM quota against a
runaway client, not against someone determined to switch names.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, per_minute: int, per_day: int):
        self.windows = ((60.0, per_minute), (86400.0, per_day))
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def blocked(self, key: str, now: float | None = None) -> float:
        """Seconds until key is under every limit again (0 = not blocked); records nothing."""
        now = time.time() if now is None else now
        with self.lock:
            hits = self.hits[key]
            for span, limit in self.windows:
                recent = [t for t in hits if t > now - span]
                if len(recent) >= limit:
                    return round(recent[0] + span - now, 1)
            return 0.0

    def check(self, key: str, now: float | None = None) -> float:
        """Record a hit and return 0, or return the seconds until one is allowed (nothing recorded)."""
        now = time.time() if now is None else now
        with self.lock:
            hits = self.hits[key]
            while hits and hits[0] <= now - self.windows[-1][0]:
                hits.popleft()
            for span, limit in self.windows:
                recent = [t for t in hits if t > now - span]
                if len(recent) >= limit:
                    return round(recent[0] + span - now, 1)
            hits.append(now)
            return 0.0
