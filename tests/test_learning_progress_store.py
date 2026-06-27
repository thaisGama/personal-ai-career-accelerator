"""Tests for learning progress persistence helpers."""

from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.learning_progress_store import (
    append_week_from_plan,
    compute_week_status,
    ensure_learning_progress_file,
    find_week_and_day,
    load_learning_progress,
    recompute_progress_statuses,
    save_learning_progress,
    update_day_learning_unit_path,
    update_day_quiz_path,
    update_day_validation_result,
)


def test_ensure_learning_progress_file_creates_empty_progress(tmp_path: Path):
    progress_path = tmp_path / "data" / "learning_progress.json"

    ensure_learning_progress_file(progress_path, roadmap_id="goal_test")

    progress = load_learning_progress(progress_path)
    assert progress == {
        "roadmap_id": "goal_test",
        "status": "TODO",
        "weeks": [],
    }


def test_save_and_load_learning_progress(tmp_path: Path):
    progress_path = tmp_path / "data" / "learning_progress.json"
    expected = {
        "roadmap_id": "goal_test",
        "status": "TODO",
        "weeks": [{"week_id": "week_001", "days": []}],
    }

    save_learning_progress(progress_path, expected)

    assert load_learning_progress(progress_path) == expected


def test_append_week_from_plan_creates_week_with_days(tmp_path: Path):
    progress_path = tmp_path / "data" / "learning_progress.json"
    plan_md = """# Week 1 Learning Plan

🧩 Learning Days (10–30 min)
- 🔥 **Day 1 (20 min): What is an LLM?** [phase:P1][milestone:M1.1][depth:intro]
- ⭐ **Day 2 (15 min): Prompt and tool basics** [phase:P1][milestone:M1.1][depth:intro]

🧪 Mini Project for the Week
Title: Example
"""

    progress, week = append_week_from_plan(
        path=progress_path,
        plan_md=plan_md,
        roadmap_id="goal_test",
        phase_id="P1",
        milestone_id="M1.1",
        week_number_global=1,
        goal="Understand basic LLM behavior.",
    )

    assert progress["roadmap_id"] == "goal_test"
    assert week["week_id"] == "week_001"
    assert week["phase_id"] == "P1"
    assert week["milestone_id"] == "M1.1"
    assert week["week_number_global"] == 1
    assert week["week_number_in_milestone"] == 1
    assert week["estimated_minutes"] == 35
    assert week["status"] == "TODO"
    assert [day["day_id"] for day in week["days"]] == ["day_001", "day_002"]
    assert [day["day_number"] for day in week["days"]] == [1, 2]
    assert [day["topic"] for day in week["days"]] == [
        "What is an LLM?",
        "Prompt and tool basics",
    ]
    assert week["days"][0]["estimated_minutes"] == 20
    assert week["days"][0]["status"] == "TODO"
    assert week["days"][0]["quiz_result"] == ""
    assert week["days"][0]["is_review"] is False


def test_append_week_from_plan_infers_week_links_from_day_tags(tmp_path: Path):
    progress_path = tmp_path / "data" / "learning_progress.json"
    plan_md = """# Week 1 Learning Plan

🧩 Learning Days (10–30 min)
- 🔥 **Day 1 (20 min): What is an LLM?** [phase:P1][milestone:M1.1][depth:intro]
- ⭐ **Day 2 (15 min): Prompt and tool basics** [phase:P1][milestone:M1.1][depth:intro]
"""

    _progress, week = append_week_from_plan(
        path=progress_path,
        plan_md=plan_md,
        roadmap_id="goal_test",
        goal="Understand basic LLM behavior.",
    )

    assert week["phase_id"] == "P1"
    assert week["milestone_id"] == "M1.1"
    assert week["week_number_in_milestone"] == 1
    assert week["estimated_minutes"] == 35
    assert [day["topic"] for day in week["days"]] == [
        "What is an LLM?",
        "Prompt and tool basics",
    ]


def test_append_week_from_plan_uses_deterministic_next_ids(tmp_path: Path):
    progress_path = tmp_path / "data" / "learning_progress.json"
    first_plan = """🧩 Learning Days (10–30 min)
- 🔥 **Day 1 (20 min): First topic**
"""
    second_plan = """🧩 Learning Days (10–30 min)
- 🔥 **Day 1 (25 min): Second topic**
"""

    append_week_from_plan(progress_path, first_plan, roadmap_id="goal_test", milestone_id="M1.1")
    _progress, week = append_week_from_plan(
        progress_path,
        second_plan,
        roadmap_id="goal_test",
        milestone_id="M1.1",
    )

    assert week["week_id"] == "week_002"
    assert week["week_number_global"] == 2
    assert week["week_number_in_milestone"] == 2
    assert week["days"][0]["day_id"] == "day_002"


def test_update_day_learning_unit_path_updates_matching_day(tmp_path: Path):
    progress_path = tmp_path / "data" / "learning_progress.json"
    append_week_from_plan(
        progress_path,
        """🧩 Learning Days (10–30 min)
- 🔥 **Day 1 (20 min): First topic**
""",
        roadmap_id="goal_test",
    )

    progress, week, day = update_day_learning_unit_path(
        progress_path,
        day_id="day_001",
        learning_unit_path="docs/learning_units/day_001_first-topic.md",
    )

    assert week["week_id"] == "week_001"
    assert day["learning_unit_path"] == "docs/learning_units/day_001_first-topic.md"
    _loaded_week, loaded_day = find_week_and_day(progress, "day_001")
    assert loaded_day["learning_unit_path"] == "docs/learning_units/day_001_first-topic.md"
    assert load_learning_progress(progress_path)["weeks"][0]["days"][0]["learning_unit_path"] == (
        "docs/learning_units/day_001_first-topic.md"
    )


def test_update_day_quiz_path_updates_matching_day_without_status_change(tmp_path: Path):
    progress_path = tmp_path / "data" / "learning_progress.json"
    append_week_from_plan(
        progress_path,
        """🧩 Learning Days (10–30 min)
- 🔥 **Day 1 (20 min): First topic**
""",
        roadmap_id="goal_test",
    )

    _progress, _week, day = update_day_quiz_path(
        progress_path,
        day_id="day_001",
        quiz_path="docs/quizzes/day_001_first-topic.md",
    )

    assert day["quiz_path"] == "docs/quizzes/day_001_first-topic.md"
    assert day["status"] == "TODO"
    assert day["quiz_result"] == ""


def test_update_day_validation_result_passes_day(tmp_path: Path):
    progress_path = tmp_path / "data" / "learning_progress.json"
    append_week_from_plan(
        progress_path,
        """🧩 Learning Days (10–30 min)
- 🔥 **Day 1 (20 min): First topic**
""",
        roadmap_id="goal_test",
    )

    _progress, _week, day = update_day_validation_result(
        progress_path,
        day_id="day_001",
        quiz_result="PASS",
        reflection="This clicked.",
        completed_at="2026-06-27T18:30:00+00:00",
    )

    assert day["status"] == "PASSED"
    assert day["quiz_result"] == "PASS"
    assert day["completed_at"] == "2026-06-27T18:30:00+00:00"
    assert day["reflection"] == "This clicked."
    assert day["review_reason"] == ""
    assert _week["status"] == "PASSED"


def test_update_day_validation_result_fails_day(tmp_path: Path):
    progress_path = tmp_path / "data" / "learning_progress.json"
    append_week_from_plan(
        progress_path,
        """🧩 Learning Days (10–30 min)
- 🔥 **Day 1 (20 min): First topic**
""",
        roadmap_id="goal_test",
    )

    _progress, _week, day = update_day_validation_result(
        progress_path,
        day_id="day_001",
        quiz_result="FAIL",
        reflection="I need another pass.",
        review_reason="Weak areas: terminology.",
        completed_at="2026-06-27T18:30:00+00:00",
    )

    assert day["status"] == "NEEDS_REVIEW"
    assert day["quiz_result"] == "FAIL"
    assert day["completed_at"] == "2026-06-27T18:30:00+00:00"
    assert day["reflection"] == "I need another pass."
    assert day["review_reason"] == "Weak areas: terminology."
    assert _week["status"] == "NEEDS_REVIEW"


def test_compute_week_status_from_day_statuses():
    assert compute_week_status({"days": []}) == "TODO"
    assert compute_week_status({"days": [{"status": "TODO"}, {"status": "TODO"}]}) == "TODO"
    assert compute_week_status({"days": [{"status": "PASSED"}, {"status": "TODO"}]}) == "IN_PROGRESS"
    assert compute_week_status({"days": [{"status": "IN_PROGRESS"}, {"status": "TODO"}]}) == "IN_PROGRESS"
    assert compute_week_status({"days": [{"status": "PASSED"}, {"status": "PASSED"}]}) == "PASSED"
    assert compute_week_status({"days": [{"status": "PASSED"}, {"status": "NEEDS_REVIEW"}]}) == "NEEDS_REVIEW"


def test_recompute_progress_statuses_rolls_up_week_milestone_phase_and_roadmap():
    progress = {
        "roadmap_id": "goal_test",
        "status": "TODO",
        "weeks": [
            {
                "week_id": "week_001",
                "phase_id": "P1",
                "milestone_id": "M1.1",
                "status": "TODO",
                "days": [{"day_id": "day_001", "status": "PASSED"}],
            },
            {
                "week_id": "week_002",
                "phase_id": "P1",
                "milestone_id": "M1.1",
                "status": "TODO",
                "days": [{"day_id": "day_002", "status": "TODO"}],
            },
            {
                "week_id": "week_003",
                "phase_id": "P2",
                "milestone_id": "M2.1",
                "status": "TODO",
                "days": [{"day_id": "day_003", "status": "TODO"}],
            },
        ],
    }

    recompute_progress_statuses(progress)

    assert [week["status"] for week in progress["weeks"]] == ["PASSED", "TODO", "TODO"]
    assert progress["milestones"] == [
        {"milestone_id": "M1.1", "phase_id": "P1", "status": "IN_PROGRESS"},
        {"milestone_id": "M2.1", "phase_id": "P2", "status": "TODO"},
    ]
    assert progress["phases"] == [
        {"phase_id": "P1", "status": "IN_PROGRESS"},
        {"phase_id": "P2", "status": "TODO"},
    ]
    assert progress["status"] == "IN_PROGRESS"


def test_recompute_progress_statuses_needs_review_takes_precedence():
    progress = {
        "roadmap_id": "goal_test",
        "status": "TODO",
        "weeks": [
            {
                "week_id": "week_001",
                "phase_id": "P1",
                "milestone_id": "M1.1",
                "status": "TODO",
                "days": [{"day_id": "day_001", "status": "PASSED"}],
            },
            {
                "week_id": "week_002",
                "phase_id": "P1",
                "milestone_id": "M1.1",
                "status": "TODO",
                "days": [{"day_id": "day_002", "status": "NEEDS_REVIEW"}],
            },
        ],
    }

    recompute_progress_statuses(progress)

    assert [week["status"] for week in progress["weeks"]] == ["PASSED", "NEEDS_REVIEW"]
    assert progress["milestones"][0]["status"] == "NEEDS_REVIEW"
    assert progress["phases"][0]["status"] == "NEEDS_REVIEW"
    assert progress["status"] == "NEEDS_REVIEW"


def test_update_day_validation_result_recomputes_parent_statuses(tmp_path: Path):
    progress_path = tmp_path / "data" / "learning_progress.json"
    append_week_from_plan(
        progress_path,
        """🧩 Learning Days (10–30 min)
- 🔥 **Day 1 (20 min): First topic** [phase:P1][milestone:M1.1]
- ⭐ **Day 2 (15 min): Second topic** [phase:P1][milestone:M1.1]
""",
        roadmap_id="goal_test",
    )

    progress, week, _day = update_day_validation_result(
        progress_path,
        day_id="day_001",
        quiz_result="PASS",
        completed_at="2026-06-27T18:30:00+00:00",
    )

    assert week["status"] == "IN_PROGRESS"
    assert progress["milestones"][0]["status"] == "IN_PROGRESS"
    assert progress["phases"][0]["status"] == "IN_PROGRESS"
    assert progress["status"] == "IN_PROGRESS"

    progress, week, _day = update_day_validation_result(
        progress_path,
        day_id="day_002",
        quiz_result="PASS",
        completed_at="2026-06-27T18:40:00+00:00",
    )

    assert week["status"] == "PASSED"
    assert progress["milestones"][0]["status"] == "PASSED"
    assert progress["phases"][0]["status"] == "PASSED"
    assert progress["status"] == "PASSED"
