"""Tests for learning unit quality checks."""

from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.weekly_planner import check_learning_unit_quality


def test_learning_quality_bad_unit_flags_missing_elements():
    bad_md = """# Learning Unit: Test

## Decision Lens (use when / don't use when)
- Use when:
  - Quick wins
- Don't use when:
  - None

## Mental Model
- A short overview.

## Operational Playbook (How You Use This at Work)
- Use the Magic Prompting Strategy.

## Worked Examples
- Example 1:
  - Problem: do a thing.
- Example 2:
  - Problem: do a thing.
- Example 3:
  - Problem: do a thing.

## Mini-Project Blueprint
- Input format:
"""
    result = check_learning_unit_quality(bad_md)

    assert result["ok"] is False
    assert result["missing_definitions"]
    assert result["has_exercise_and_selfcheck"] is False
    assert result["decision_lens_ok"] is False


def test_learning_quality_good_unit_passes():
    good_md = """# Learning Unit: Test

## Decision Lens (use when / don't use when)
- Use when:
  - You need a quick baseline.
  - You have small scope tasks.
- Don't use when:
  - You need deterministic guarantees; use a deterministic script.
  - You must meet strict compliance requirements; use a rules engine.

## Mental Model
- A short overview.

## Operational Playbook (How You Use This at Work)
- Baseline approach means a simple first-pass method for quick results.

## Worked Examples
- Example 1:
  - Problem: naive baseline.
  - Practical approach: simple baseline.
- Example 2:
  - Problem: structured template.
  - Practical approach: steps and schema.
- Example 3:
  - Problem: constrained evaluation.
  - Practical approach: constraints and evaluation checklist.

## Mini-Project Blueprint
- Input format:

## Exercise (5-15 min)
- Try this: write a tiny checklist.

## Self-check rubric
- I can explain the baseline approach.
- I can list constraints and evaluation steps.
"""
    result = check_learning_unit_quality(good_md)

    assert result["ok"] is True
    assert result["issues"] == []


def test_learning_quality_decision_lens_too_shallow():
    md = """# Learning Unit: Test

## Decision Lens (use when / don't use when)
- Use when:
  - One case.
- Don't use when:
  - One case.

## Worked Examples
- Example 1:
  - Problem: naive baseline.
- Example 2:
  - Problem: structured template.
- Example 3:
  - Problem: constrained evaluation checklist.

## Mini-Project Blueprint
- Input format:

## Exercise (5-15 min)
- Try this: write a tiny checklist.

## Self-check rubric
- I can explain the baseline approach.
"""
    result = check_learning_unit_quality(md)

    assert result["ok"] is False
    assert result["decision_lens_ok"] is False
