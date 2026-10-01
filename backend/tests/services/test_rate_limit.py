"""``RateLimiter``: an in-memory token bucket per key (DECISIONS.md D5).

The limiter takes its clock as an argument, so these tests move time by hand
instead of sleeping.
"""

import threading

from app.services.rate_limit import RateLimiter

# D5's login limit: 5 per minute, i.e. a bucket of 5 that refills one token
# every 12 seconds.
CAPACITY = 5
PER_SECOND = 5 / 60
ONE_TOKEN = 12.0  # seconds


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0  # monotonic clocks do not start at 0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _limiter(clock: FakeClock) -> RateLimiter:
    return RateLimiter(capacity=CAPACITY, refill_per_second=PER_SECOND, clock=clock)


def _allowed(limiter: RateLimiter, key: str, times: int) -> int:
    """How many of ``times`` back-to-back requests get through."""
    return sum(limiter.allow(key) for _ in range(times))


# --- the bucket --------------------------------------------------------------


def test_a_new_key_gets_a_full_bucket() -> None:
    limiter = _limiter(FakeClock())

    assert _allowed(limiter, "1.2.3.4", CAPACITY) == CAPACITY


def test_an_empty_bucket_refuses() -> None:
    limiter = _limiter(FakeClock())
    _allowed(limiter, "1.2.3.4", CAPACITY)

    assert limiter.allow("1.2.3.4") is False


def test_one_token_comes_back_after_its_refill_time() -> None:
    clock = FakeClock()
    limiter = _limiter(clock)
    _allowed(limiter, "1.2.3.4", CAPACITY)

    clock.advance(ONE_TOKEN)

    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is False


def test_half_a_token_is_not_enough() -> None:
    clock = FakeClock()
    limiter = _limiter(clock)
    _allowed(limiter, "1.2.3.4", CAPACITY)

    clock.advance(ONE_TOKEN / 2)

    assert limiter.allow("1.2.3.4") is False


def test_halves_add_up() -> None:
    # Refill is continuous: two half-waits make one token, even with a
    # refused request in between.
    clock = FakeClock()
    limiter = _limiter(clock)
    _allowed(limiter, "1.2.3.4", CAPACITY)

    clock.advance(ONE_TOKEN / 2)
    assert limiter.allow("1.2.3.4") is False
    clock.advance(ONE_TOKEN / 2)

    assert limiter.allow("1.2.3.4") is True


def test_the_bucket_never_holds_more_than_its_capacity() -> None:
    clock = FakeClock()
    limiter = _limiter(clock)

    clock.advance(3600)  # an hour of refill, but the bucket holds 5

    assert _allowed(limiter, "1.2.3.4", CAPACITY + 10) == CAPACITY


def test_refused_requests_do_not_cost_tokens() -> None:
    # Hammering an empty bucket must not push the next token further away.
    clock = FakeClock()
    limiter = _limiter(clock)
    _allowed(limiter, "1.2.3.4", CAPACITY)

    for _ in range(100):
        limiter.allow("1.2.3.4")
    clock.advance(ONE_TOKEN)

    assert limiter.allow("1.2.3.4") is True


def test_keys_have_separate_buckets() -> None:
    limiter = _limiter(FakeClock())
    _allowed(limiter, "1.2.3.4", CAPACITY)

    assert limiter.allow("5.6.7.8") is True


def test_capacity_is_the_burst_allowance() -> None:
    # D5's game-input shape: 1 per second sustained, short bursts allowed.
    clock = FakeClock()
    limiter = RateLimiter(capacity=3, refill_per_second=1.0, clock=clock)

    assert _allowed(limiter, "session-1", 4) == 3
    clock.advance(1.0)
    assert _allowed(limiter, "session-1", 2) == 1


# --- concurrency -------------------------------------------------------------


def test_concurrent_requests_cannot_overdraw_the_bucket() -> None:
    # Sync endpoints run in a thread pool, so two requests can take from the
    # same bucket at once. The clock is frozen: exactly CAPACITY may pass.
    # (A race without the lock is rare, so passing does not prove the lock is
    # needed; this guards against a change that makes the race common.)
    limiter = _limiter(FakeClock())
    threads_count = 50
    barrier = threading.Barrier(threads_count)
    results: list[bool] = []
    results_lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        allowed = limiter.allow("1.2.3.4")
        with results_lock:
            results.append(allowed)

    threads = [threading.Thread(target=worker) for _ in range(threads_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results.count(True) == CAPACITY


# --- forgetting full buckets -------------------------------------------------
# A full bucket behaves exactly like a missing one, so the limiter drops full
# buckets every ``capacity / refill_per_second`` seconds (60 s here: the time an
# empty bucket takes to fill). Memory then holds only recently active keys.

SWEEP_EVERY = CAPACITY / PER_SECOND  # 60 seconds


def test_full_buckets_are_forgotten_after_the_sweep_interval() -> None:
    clock = FakeClock()
    limiter = _limiter(clock)
    for i in range(100):
        limiter.allow(f"10.0.0.{i}")
    assert len(limiter) == 100

    clock.advance(SWEEP_EVERY)
    limiter.allow("1.2.3.4")  # any call may sweep

    assert len(limiter) == 1  # only the newcomer


def test_nothing_is_forgotten_before_the_sweep_interval() -> None:
    clock = FakeClock()
    limiter = _limiter(clock)
    for i in range(100):
        limiter.allow(f"10.0.0.{i}")

    clock.advance(SWEEP_EVERY - 1)
    limiter.allow("1.2.3.4")

    assert len(limiter) == 101


def test_a_bucket_still_refilling_is_kept() -> None:
    # Forgetting it would hand that key a full bucket: free attempts.
    clock = FakeClock()
    limiter = _limiter(clock)
    clock.advance(SWEEP_EVERY / 2)
    _allowed(limiter, "1.2.3.4", CAPACITY)  # emptied half-way to the sweep

    clock.advance(SWEEP_EVERY / 2)
    limiter.allow("5.6.7.8")  # sweeps; 1.2.3.4 holds only 2.5 tokens

    assert len(limiter) == 2
    assert _allowed(limiter, "1.2.3.4", CAPACITY) == 2


def test_a_forgotten_key_starts_again_with_a_full_bucket() -> None:
    clock = FakeClock()
    limiter = _limiter(clock)
    _allowed(limiter, "1.2.3.4", CAPACITY)

    clock.advance(SWEEP_EVERY)
    limiter.allow("5.6.7.8")  # sweeps 1.2.3.4, which had refilled

    assert _allowed(limiter, "1.2.3.4", CAPACITY + 1) == CAPACITY
