"""Wall-clock + soft-memory watchdog checked at stage boundaries.

We can't safely kill the main thread mid-native-call, so the watchdog arms a
timer that flips a flag; the pipeline calls `check()` between stages and raises
`WatchdogTimeout` (surfaced to the UI as a clean error) if the budget or memory
ceiling was exceeded. Subprocess-level hangs are already bounded by ffmpeg/ASR
timeouts elsewhere.
"""

from __future__ import annotations

import sys
import threading
import time

try:
    import resource
except Exception:  # pragma: no cover - non-POSIX
    resource = None  # type: ignore


class WatchdogTimeout(RuntimeError):
    pass


class Watchdog:
    def __init__(self, budget_sec: float = 0.0, memory_limit_mb: float = 0.0) -> None:
        self.budget = float(budget_sec or 0.0)
        self.memory_limit_mb = float(memory_limit_mb or 0.0)
        self.start = time.time()
        self._expired = threading.Event()
        self._timer: "threading.Timer | None" = None
        if self.budget > 0:
            self._timer = threading.Timer(self.budget, self._expired.set)
            self._timer.daemon = True
            self._timer.start()

    def elapsed(self) -> float:
        return time.time() - self.start

    def peak_rss_mb(self) -> "float | None":
        if resource is None:
            return None
        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # ru_maxrss is bytes on macOS, kilobytes on Linux.
        return round(ru / (1024 * 1024), 1) if sys.platform == "darwin" else round(ru / 1024, 1)

    def check(self, stage: str = "") -> None:
        if self._expired.is_set():
            raise WatchdogTimeout(f"Analysis exceeded {self.budget:.0f}s budget at stage '{stage}'")
        if self.memory_limit_mb:
            m = self.peak_rss_mb()
            if m and m > self.memory_limit_mb:
                raise WatchdogTimeout(
                    f"Analysis exceeded {self.memory_limit_mb:.0f}MB (peak {m}MB) at stage '{stage}'"
                )

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
