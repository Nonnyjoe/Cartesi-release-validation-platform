"""
services/sandbox-manager/log_buffer.py

LogBatchBuffer — thread-safe accumulator for log lines emitted during sandbox
provisioning.  Collects lines from all sources (container stdout/stderr,
subprocess output, exec_run output) and flushes them in configurable batches
so the orchestrator can persist them in one DB round-trip and broadcast them
over WebSocket in one message.

Flush triggers (whichever comes first):
  • max_lines lines have accumulated (default 50)
  • max_age_s seconds have elapsed since the last flush (default 2.0)
  • flush() or stop() is called explicitly (on teardown)

Thread safety:
  • append() is safe to call from any thread concurrently.
  • The flush callback is called from either the appending thread (when
    max_lines is hit) or the internal timer thread.  The callback must be
    thread-safe (i.e. schedule work on the async event loop via
    run_coroutine_threadsafe, not call async code directly).

Usage:
    def my_flush(batch: list[dict]):
        asyncio.run_coroutine_threadsafe(publish_log_batch(batch), loop)

    buf = LogBatchBuffer(flush_cb=my_flush)
    buf.append("advancer", "info", "Starting epoch 0")
    ...
    buf.stop()   # flush remaining lines and stop timer thread
"""

import threading
import time
from datetime import datetime, timezone
from typing import Callable, List


class LogBatchBuffer:
    """
    Thread-safe log accumulator with automatic timed and size-based flushing.

    Parameters
    ----------
    flush_cb   : callable(batch: list[dict]) — called with the accumulated lines.
                 Each element: {"source": str, "level": str, "message": str, "ts": str}
    max_lines  : flush after accumulating this many lines (default 50)
    max_age_s  : flush after this many seconds even if not full (default 2.0)
    """

    def __init__(
        self,
        flush_cb: Callable[[List[dict]], None],
        max_lines: int = 50,
        max_age_s: float = 2.0,
    ):
        self._flush_cb   = flush_cb
        self._max_lines  = max_lines
        self._max_age_s  = max_age_s

        self._lines: List[dict] = []
        self._lock        = threading.Lock()
        self._last_flush  = time.monotonic()

        # Daemon timer thread — wakes up every 500 ms to age-flush
        self._stop_event = threading.Event()
        self._timer = threading.Thread(
            target=self._timer_loop,
            daemon=True,
            name="log-batch-timer",
        )
        self._timer.start()

    # ── Public API ─────────────────────────────────────────────────────────────

    def append(self, source: str, level: str, message: str) -> None:
        """
        Add one log line.  If max_lines is reached the batch is flushed
        synchronously in the calling thread before returning.
        """
        entry = {
            "source":  source[:64],
            "level":   level,
            "message": message[:4096],
            "ts":      datetime.now(tz=timezone.utc).isoformat(),
        }
        flush_now = False
        with self._lock:
            self._lines.append(entry)
            if len(self._lines) >= self._max_lines:
                flush_now = True
        if flush_now:
            self._do_flush()

    def flush(self) -> None:
        """Force-flush any buffered lines immediately."""
        self._do_flush()

    def stop(self) -> None:
        """Signal the timer thread to stop and flush remaining lines."""
        self._stop_event.set()
        self._do_flush()

    # ── Internal ───────────────────────────────────────────────────────────────

    def _timer_loop(self) -> None:
        """Background thread: flush when max_age_s has elapsed since last flush."""
        while not self._stop_event.wait(timeout=0.5):
            if time.monotonic() - self._last_flush >= self._max_age_s:
                self._do_flush()

    def _do_flush(self) -> None:
        """Drain the buffer and invoke the flush callback (never raises)."""
        with self._lock:
            if not self._lines:
                return
            batch            = self._lines
            self._lines      = []
            self._last_flush = time.monotonic()

        try:
            self._flush_cb(batch)
        except Exception:
            # Swallow — a buffer flush error must never propagate into the
            # provisioner and kill the sandbox lifecycle.
            pass
