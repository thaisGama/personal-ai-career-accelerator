"""Tests for weekly planner helper functions.

Run with: pytest
"""

from pathlib import Path

import pytest

# Ensure project root is on sys.path for module imports.
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.weekly_planner import format_weekly_plan, save_weekly_plan


def test_format_weekly_plan_strips_whitespace():
    raw = "\n\n  # Week 1 Learning Plan\nContent\n\n"
    formatted = format_weekly_plan(raw)
    assert formatted.startswith("# Week")
    assert "Content" in formatted
    assert formatted == formatted.strip()


def test_format_weekly_plan_removes_code_fences():
    raw = "```markdown\n# Week 1 Learning Plan\nContent\n```"
    formatted = format_weekly_plan(raw)
    assert "```" not in formatted
    assert "# Week 1 Learning Plan" in formatted


def test_format_weekly_plan_inserts_heading_when_missing():
    raw = "Content without heading"
    formatted = format_weekly_plan(raw)
    assert formatted.startswith("# Week")
    assert "Content without heading" in formatted


def test_save_weekly_plan_creates_file_and_dir(tmp_path: Path):
    output_dir = tmp_path / "weekly_plans"
    markdown = "# Test Plan\nContent"

    path = save_weekly_plan(markdown, output_dir=str(output_dir))

    assert path.exists()
    assert path.suffix == ".md"
    assert path.parent == output_dir
    assert path.read_text(encoding="utf-8") == markdown.strip()


def test_save_weekly_plan_uses_custom_filename(tmp_path: Path):
    output_dir = tmp_path / "weekly_plans"
    markdown = "# Custom Plan\nContent"

    path = save_weekly_plan(markdown, output_dir=str(output_dir), filename="custom.md")

    assert path.name == "custom.md"
    assert path.exists()
    assert path.read_text(encoding="utf-8") == markdown.strip()
