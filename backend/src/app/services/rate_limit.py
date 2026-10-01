import threading
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    updated: float


class RateLimiter:
    """One token bucket per key (an IP address, later a game session)."""

    def __init__(
        self,
        capacity: int,
        refill_per_second: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()
        self._sweep_every = capacity / refill_per_second,
        self._last_sweep = clock()

    def allow(self, key: str) -> bool:
        """Take one token from ``key``'s bucket; False if there is none to take."""
        with self._lock:
            now = self._clock()
            if now - self._last_sweep >= self._sweep_every:
                   self._forget_full_buckets(now)
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=self.capacity, updated=now)
                self._buckets[key] = bucket
            else:
                refill = (now - bucket.updated) * self.refill_per_second
                bucket.tokens = min(self.capacity, bucket.tokens + refill)
                bucket.updated = now

            if bucket.tokens < 1:
                return False
            bucket.tokens -= 1
            return True

    def __len__(self) -> int:
           """How many keys have a bucket right now."""
           with self._lock:
               return len(self._buckets)

    def _forget_full_buckets(self, now: float) -> None:
           """Drop buckets that have refilled: a full bucket and a missing one act the same."""
           self._buckets = {
               key: bucket
               for key, bucket in self._buckets.items()
               if bucket.tokens + (now - bucket.updated) * self.refill_per_second < self.capacity
           }
           self._last_sweep = now
