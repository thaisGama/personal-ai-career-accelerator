"""Tests for day-specific quiz generation."""

from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent import tools
from src.agent.learning_progress_store import (
    append_week_from_plan,
    load_learning_progress,
    update_day_learning_unit_path,
)


def test_generate_quiz_for_day_saves_file_and_updates_progress(tmp_path: Path, monkeypatch):
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
    learning_unit_path = tmp_path / "docs" / "learning_units" / "day_001_what-is-an-llm.md"
    learning_unit_path.parent.mkdir(parents=True, exist_ok=True)
    learning_unit_path.write_text(
        "# Learning Unit: What is an LLM?\n\nAn LLM predicts useful next text from context.",
        encoding="utf-8",
    )
    update_day_learning_unit_path(
        progress_path,
        day_id="day_001",
        learning_unit_path="docs/learning_units/day_001_what-is-an-llm.md",
    )

    captured = {}

    def fake_call_llm(**kwargs):
        captured["user_prompt"] = kwargs["user_prompt"]
        return """<<QUIZ>>
What is an LLM?

Questions (mix of short answer + 1–2 multiple choice):
- Q1) Explain what an LLM predicts.
- Q2) What role does context play?
- Q3) Give one workplace use.
- Q4) Multiple choice: What is the best description?
- Q5) Name one limitation.
<<ANSWER_KEY>>
- Q1: Useful next text from context.
- Q2: It guides the response.
- Q3: Summarizing tickets.
- Q4: A language model.
- Q5: It can be wrong.
<<RUBRIC>>
- What "excellent" looks like: Clear and grounded.
- What "acceptable" looks like: Basic but correct.
- What "needs work" looks like: Vague or incorrect.
<<FOLLOW_UP>>
- If score <= 6/10: Review the mental model.
- If score > 6/10: Try a harder scenario.
"""

    monkeypatch.setattr(tools, "call_llm", fake_call_llm)

    result = tools.tool_generate_quiz_for_day(
        day_id="day_001",
        base_dir=tmp_path,
        model="test-model",
    )

    assert result["day_id"] == "day_001"
    assert result["quiz_path"] == "docs/quizzes/day_001_what-is-an-llm.md"
    assert "An LLM predicts useful next text from context." in captured["user_prompt"]
    saved_path = tmp_path / result["quiz_path"]
    assert saved_path.exists()
    assert "<<QUIZ>>" in saved_path.read_text(encoding="utf-8")

    progress = load_learning_progress(progress_path)
    day = progress["weeks"][0]["days"][0]
    assert day["quiz_path"] == "docs/quizzes/day_001_what-is-an-llm.md"
    assert day["status"] == "TODO"
    assert day["quiz_result"] == ""
