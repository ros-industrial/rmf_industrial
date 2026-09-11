from __future__ import annotations

import threading
from collections.abc import Callable

from ..logger import get_logger

LOGGER = get_logger(__name__)


class Heartbeat:
    """Periodic task runner. Registered callbacks fire on every tick.

    Use :meth:`add` to attach any number of zero-argument callables — for
    example, re-publishing a cached connection message or sending a
    ``stateRequest`` instant action. All callbacks share the same interval.

    ::

        hb = Heartbeat(interval=30.0)
        hb.add(lambda: pub.publish(last_connection))
        hb.add(lambda: master.publish_instant_actions(..., state_request))
        hb.start()
        # …
        hb.stop()

    The background thread is a daemon so forgetting :meth:`stop` is safe, but
    calling it enables a clean shutdown.
    """

    def __init__(self, interval: float) -> None:
        self._interval = interval
        self._callbacks: list[Callable[[], None]] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="heartbeat"
        )

    def add(self, callback: Callable[[], None]) -> None:
        """Register ``callback`` to be called on every tick."""
        with self._lock:
            self._callbacks.append(callback)

    def start(self) -> None:
        """Start the background tick thread."""
        self._thread.start()

    def stop(self) -> None:
        """Signal the tick thread to exit and wait for it to finish."""
        self._stop_event.set()
        self._thread.join()

    def _loop(self) -> None:
        while not self._stop_event.wait(self._interval):
            with self._lock:
                callbacks = list(self._callbacks)
            for cb in callbacks:
                try:
                    cb()
                except Exception as exc:  # noqa: BLE001 — user callback may raise anything
                    LOGGER.warning("Heartbeat callback failed: %s", exc)
