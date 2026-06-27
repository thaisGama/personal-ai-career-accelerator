"""Tests for review day generation."""

from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent import tools
from src.agent.learning_progress_store import append_week_from_plan, load_learning_progress, update_day_validation_result


def test_generate_review_day_appends_review_day_without_artifact_generation(tmp_path: Path):
    progress_path = tmp_path / "data" / "learning_progress.json"
    append_week_from_plan(
        progress_path,
        """# Week 1 Learning Plan

🧩 Learning Days (10–30 min)
- 🔥 **Day 1 (20 min): What is an LLM?** [phase:P1][milestone:M1.1]
""",
        roadmap_id="goal_test",
        phase_id="P1",
        milestone_id="M1.1",
        week_number_global=1,
        goal="Understand basic LLM behavior.",
    )
    update_day_validation_result(
        progress_path,
        day_id="day_001",
        quiz_result="FAIL",
        review_reason="Weak answer on LLM concepts.",
    )

    result = tools.tool_generate_review_day(
        failed_day_id="day_001",
        base_dir=tmp_path,
        model="test-model",
    )

    assert result["failed_day_id"] == "day_001"
    assert result["review_day_id"] == "day_002"
    assert result["learning_unit_path"] == ""
    assert result["quiz_path"] == ""
    assert result["week_status"] == "NEEDS_REVIEW"

    progress = load_learning_progress(progress_path)
    week = progress["weeks"][0]
    assert len(week["days"]) == 2
    assert week["days"][0]["status"] == "NEEDS_REVIEW"
    assert week["days"][1]["is_review"] is True
    assert week["days"][1]["review_of_day_id"] == "day_001"
    assert week["days"][1]["topic"] == "Review: What is an LLM?"
