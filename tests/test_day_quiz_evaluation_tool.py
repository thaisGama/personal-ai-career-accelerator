"""Tests for day-specific quiz evaluation."""

from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent import tools
from src.agent.learning_progress_store import append_week_from_plan, load_learning_progress, update_day_quiz_path


def _seed_day_with_quiz(tmp_path: Path) -> Path:
    progress_path = tmp_path / "data" / "learning_progress.json"
    append_week_from_plan(
        progress_path,
        """# Week 1 Learning Plan

🧩 Learning Days (10–30 min)
- 🔥 **Day 1 (20 min): What is an LLM?** [phase:P1][milestone:M1.1][depth:intro]
""",
        roadmap_id="goal_test",
        phase_id="P1",
        milestone_id="M1.1",
        week_number_global=1,
        goal="Understand basic LLM behavior.",
    )
    quiz_path = tmp_path / "docs" / "quizzes" / "day_001_what-is-an-llm.md"
    quiz_path.parent.mkdir(parents=True, exist_ok=True)
    quiz_path.write_text("<<QUIZ>>\nQ1) What is an LLM?\n<<ANSWER_KEY>>\n- Q1: A language model.", encoding="utf-8")
    update_day_quiz_path(progress_path, day_id="day_001", quiz_path="docs/quizzes/day_001_what-is-an-llm.md")
    return progress_path


def test_evaluate_quiz_for_day_maps_move_on_to_pass_even_with_low_score(tmp_path: Path, monkeypatch):
    progress_path = _seed_day_with_quiz(tmp_path)
    monkeypatch.setattr(
        tools,
        "evaluate_micro_quiz",
        lambda **_kwargs: {
            "raw_evaluation": "raw",
            "eval_block": "- Score: 2/10\n- Move-on decision: MOVE_ON",
            "score": 2.0,
            "mastery": "LOW",
            "move_on_decision": "MOVE_ON",
        },
    )

    result = tools.tool_evaluate_quiz_for_day(
        day_id="day_001",
        learner_answers="answer",
        base_dir=tmp_path,
        model="test-model",
        reflection="I can explain it now.",
    )

    assert result["quiz_result"] == "PASS"
    assert result["status"] == "PASSED"
    assert result["review_reason"] == ""
    progress = load_learning_progress(progress_path)
    day = progress["weeks"][0]["days"][0]
    assert day["quiz_result"] == "PASS"
    assert day["status"] == "PASSED"
    assert day["reflection"] == "I can explain it now."


def test_evaluate_quiz_for_day_maps_repeat_to_fail_even_with_high_score(tmp_path: Path, monkeypatch):
    progress_path = _seed_day_with_quiz(tmp_path)
    monkeypatch.setattr(
        tools,
        "evaluate_micro_quiz",
        lambda **_kwargs: {
            "raw_evaluation": "raw",
            "eval_block": "- Score: 10/10\n- Weak areas: missed context\n- Next practice (10-15 min): retry\n- Move-on decision: REPEAT",
            "score": 10.0,
            "mastery": "SOLID",
            "move_on_decision": "REPEAT",
        },
    )

    result = tools.tool_evaluate_quiz_for_day(
        day_id="day_001",
        learner_answers="answer",
        base_dir=tmp_path,
        model="test-model",
        reflection="Need review.",
    )

    assert result["quiz_result"] == "FAIL"
    assert result["status"] == "NEEDS_REVIEW"
    assert "Weak areas: missed context" in result["review_reason"]
    progress = load_learning_progress(progress_path)
    day = progress["weeks"][0]["days"][0]
    assert day["quiz_result"] == "FAIL"
    assert day["status"] == "NEEDS_REVIEW"
    assert day["reflection"] == "Need review."
