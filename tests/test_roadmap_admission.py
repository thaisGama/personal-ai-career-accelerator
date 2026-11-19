"""UTC rollover and process lifetime behavior, with a controlled clock."""

from datetime import date
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from standalone_roadmap.admission import AdmissionController, RoadmapUnavailableError
from standalone_roadmap.config import RoadmapConfig

CONFIG = RoadmapConfig("beta", True, 1)


def test_daily_quota_resets_at_utc_date_boundary():
    day = [date(2026, 10, 31)]
    controller = AdmissionController(today=lambda: day[0])
    with controller.admit(CONFIG):
        pass
    with pytest.raises(RoadmapUnavailableError, match="allowance"):
        with controller.admit(CONFIG):
            pytest.fail("Quota exhausted")
    day[0] = date(2026, 11, 1)
    with controller.admit(CONFIG):
        pass
    with pytest.raises(RoadmapUnavailableError, match="allowance"):
        with controller.admit(CONFIG):
            pytest.fail("New day's quota exhausted")


def test_midnight_does_not_release_active_generation():
    day = [date(2026, 10, 31)]
    controller = AdmissionController(today=lambda: day[0])
    with controller.admit(CONFIG):
        day[0] = date(2026, 11, 1)
        with pytest.raises(RoadmapUnavailableError, match="being generated"):
            with controller.admit(CONFIG):
                pytest.fail("Previous day's generation is still active")
    with controller.admit(CONFIG):
        pass


def test_new_process_controller_has_fresh_allowance():
    controller = AdmissionController()
    with controller.admit(CONFIG):
        pass
    with pytest.raises(RoadmapUnavailableError):
        with controller.admit(CONFIG):
            pytest.fail("Quota exhausted")
    with AdmissionController().admit(CONFIG):
        pass
