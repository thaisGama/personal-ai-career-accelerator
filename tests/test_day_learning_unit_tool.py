"""Tests for day-specific learning unit generation."""

from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.learning_progress_store import append_week_from_plan, load_learning_progress
from src.agent import tools


def test_generate_learning_unit_for_day_saves_file_and_updates_progress(tmp_path: Path, monkeypatch):
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

    monkeypatch.setattr(
        tools,
        "call_llm",
        lambda **_kwargs: """<<LEARNING_UNIT>>
# Learning Unit: What is an LLM?

## Decision Lens (use when / don't use when)
- Use when: you need a practical mental model.
- Don't use when: you need model training internals.

## Mental Model
- An LLM predicts useful next text from context.

## How It Works (No Math)
- It uses patterns learned during training to respond to prompts.

## Operational Playbook (How You Use This at Work)
- Define the task.
- Provide context.
- Check the output.
- Failure mode: vague prompt. Fix: add constraints.
- Failure mode: missing context. Fix: include examples.

## Worked Examples
- Example 1:
  - Problem: Summarize a ticket.
  - Naive approach + why it fails: too vague.
  - Practical approach: add role, task, and output format.
  - Two tuning levers: context and constraints.
  - Debug checklist: check facts.
  - System sketch: input -> prompt -> output
- Example 2:
  - Problem: Draft release notes.
  - Naive approach + why it fails: misses audience.
  - Practical approach: include audience.
  - Two tuning levers: tone and structure.
  - Debug checklist: verify scope.
  - System sketch: notes -> prompt -> draft
- Example 3:
  - Problem: Review support logs.
  - Naive approach + why it fails: unbounded.
  - Practical approach: define categories.
  - Two tuning levers: labels and examples.
  - Debug checklist: sample manually.
  - System sketch: logs -> prompt -> labels

## Mini-Project Blueprint
- Input format: one ticket.
- Data structures (example fields/tables): title, description.
- Pipeline steps: read, prompt, review.
- What to tune: constraints.
- Debugging checklist (>=6 items): facts, scope, tone, format, examples, omissions.
- Definition of done (DoD): output is usable.
- Timeboxing:
  - MVP in 60–120 min: one prompt.
  - Stretch: compare prompts.

## Exercise (5–15 min)
- Explain an LLM in your own words.

## Self-check rubric
- Clear.
- Practical.
<<END_LEARNING_UNIT>>""",
    )
    monkeypatch.setattr(tools, "check_learning_unit_quality", lambda _md: {"ok": True})

    result = tools.tool_generate_learning_unit_for_day(
        day_id="day_001",
        base_dir=tmp_path,
        model="test-model",
    )

    assert result["day_id"] == "day_001"
    assert result["learning_unit_path"] == "docs/learning_units/day_001_what-is-an-llm.md"
    saved_path = tmp_path / result["learning_unit_path"]
    assert saved_path.exists()
    assert "# Learning Unit: What is an LLM?" in saved_path.read_text(encoding="utf-8")

    progress = load_learning_progress(progress_path)
    day = progress["weeks"][0]["days"][0]
    assert day["learning_unit_path"] == "docs/learning_units/day_001_what-is-an-llm.md"
