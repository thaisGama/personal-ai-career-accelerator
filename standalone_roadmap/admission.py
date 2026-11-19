"""Thread-safe admission shared by all sessions in this Python process."""

from contextlib import contextmanager
from datetime import date, datetime, timezone
from threading import Lock
from typing import Callable, Iterator

from .config import RoadmapConfig


class RoadmapUnavailableError(Exception):
    """An admission refusal with a message safe to display to the learner."""


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


class AdmissionController:
    def __init__(self, today: Callable[[], date] = _utc_today):
        self._today = today
        self._lock = Lock()
        self._day: date | None = None
        self._attempts = 0
        self._active = False

    @contextmanager
    def admit(self, config: RoadmapConfig) -> Iterator[None]:
        """Count only admitted attempts; never hold the lock during generation."""
        with self._lock:
            if not config.generation_enabled:
                raise RoadmapUnavailableError(
                    "Roadmap generation is temporarily disabled. Please try again later."
                )
            today = self._today()
            if today != self._day:
                self._day = today
                self._attempts = 0
            if self._active:
                raise RoadmapUnavailableError(
                    "A roadmap is being generated. Please try again when it finishes."
                )
            if config.daily_limit is not None and self._attempts >= config.daily_limit:
                raise RoadmapUnavailableError(
                    "Today's roadmap allowance has been reached. Please try again after midnight UTC."
                )
            self._attempts += 1
            self._active = True
        try:
            yield
        finally:
            with self._lock:
                self._active = False


# Imported modules survive ordinary Streamlit script reruns. Do not put this in
# session_state or cache it by configuration: either would split/reset the quota.
admission_controller = AdmissionController()
