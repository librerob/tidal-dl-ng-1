import random
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from threading import Lock

from tidalapi.exceptions import TooManyRequests


def retry_after(error: TooManyRequests) -> float:
    response = getattr(error, "response", None)
    value = response.headers.get("Retry-After") if response is not None else None
    if not value:
        return 0.0
    if value.isascii() and value.isdecimal():
        try:
            return float(int(value))
        except (ValueError, OverflowError):
            return 0.0
    try:
        until = parsedate_to_datetime(value)
        if until.tzinfo is None:
            until = until.replace(tzinfo=UTC)
        return max(0.0, (until - datetime.now(UTC)).total_seconds())
    except (ValueError, TypeError, OverflowError, IndexError):
        return 0.0


class DownloadStopped(Exception):
    pass


class RateLimit:
    def __init__(self, abort, settings):
        self.abort = abort
        self.settings = settings
        self.lock = Lock()
        self.until = 0.0
        self.failures = 0
        self.open = False

    def resume(self):
        with self.lock:
            self.failures = 0
            self.open = False

    def wait(self):
        while True:
            with self.lock:
                if self.open or self.abort.is_set():
                    raise DownloadStopped
                remaining = self.until - time.monotonic()
            if remaining <= 0:
                return
            self.abort.wait(min(remaining, 0.25))

    def record_limit(self, error, attempt=0):
        delay = max(retry_after(error), 2 ** min(attempt, 6) + random.SystemRandom().uniform(0, 1))
        with self.lock:
            self.until = max(self.until, time.monotonic() + delay)
            self.failures += 1
            if self.failures >= max(1, self.settings.rate_limit_breaker_threshold):
                self.open = True

    def call(self, operation):
        attempts = max(1, self.settings.rate_limit_attempts)
        for attempt in range(attempts):
            self.wait()
            try:
                result = operation()
            except TooManyRequests as error:
                self.record_limit(error, attempt)
                if self.open or attempt + 1 == attempts:
                    raise
            else:
                with self.lock:
                    self.failures = 0
                return result
