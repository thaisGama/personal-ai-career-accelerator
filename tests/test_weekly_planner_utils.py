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

from src.agent.weekly_planner import (
    enforce_week_heading,
    extract_between,
    extract_learning_unit,
    format_weekly_plan,
    remove_duplicate_daily_breakdown_sections,
    save_weekly_plan,
    split_markdown_into_plan_and_linkedin,
)
from src.agent.weekly_planner import build_weekly_planner_prompt


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


def test_remove_duplicate_daily_breakdown_sections_keeps_one_heading():
    raw = """# Week 1 Learning Plan

🗓️ Daily Breakdown
- Day 1: Foundations
- Day 2: Practice
- Day 3: Review

🗓️ Daily Breakdown
- Day 1: Foundations
- Day 2: Practice
- Day 3: Review
Day 1: Foundations
Day 2: Practice
Day 3: Review

🧩 Learning Days
- Day 1
"""

    cleaned = remove_duplicate_daily_breakdown_sections(raw)

    assert cleaned.count("Daily Breakdown") == 1
    assert cleaned.count("Day 1: Foundations") == 1
    assert cleaned.count("Day 2: Practice") == 1
    assert cleaned.count("Day 3: Review") == 1
    assert "- Day 1: Foundations" in cleaned
    assert "\nDay 1: Foundations" not in cleaned
    assert "🧩 Learning Days" in cleaned


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


def test_build_weekly_planner_prompt_includes_memory_audit_when_used():
    system_prompt, _ = build_weekly_planner_prompt(
        goal="Test goal",
        time_per_week_hours=2.0,
        max_session_minutes=30,
        preferences=None,
        memory_context="Some prior memory content",
        memory_used=True,
        memory_source="docs/memory.md",
        memory_char_count=123,
        task_progress=None,
        week_number=1,
    )

    assert "MEMORY_AUDIT (must be echoed exactly at the very top of the output):" in system_prompt
    assert "Memory used: YES" in system_prompt
    assert "Memory source: docs/memory.md" in system_prompt
    assert "Memory characters injected: 123" in system_prompt
    assert "🧩 Learning Days" in system_prompt
    assert "Day 1" in system_prompt
    assert "Task 1" not in system_prompt
    assert "Micro Tasks" not in system_prompt


def test_build_weekly_planner_prompt_includes_memory_audit_when_not_used():
    system_prompt, _ = build_weekly_planner_prompt(
        goal="Test goal",
        time_per_week_hours=2.0,
        max_session_minutes=30,
        preferences=None,
        memory_context="No memory content",
        memory_used=False,
        memory_source="docs/memory.md",
        memory_char_count=0,
        task_progress=None,
        week_number=1,
    )

    assert "Memory used: NO" in system_prompt
    assert "Memory characters injected: 0" in system_prompt


def test_extracts_plan_learning_unit_and_memory_blocks():
    raw = """
MEMORY_AUDIT (must be echoed exactly at the very top of the output):
Memory used: NO
Memory source: docs/memory.md
Memory characters injected: 0
Memory focus: None

<<PLAN_MARKDOWN>>
# Week 1 Learning Plan
Content
## 🔗 LinkedIn Post Template
LinkedIn
<<END_PLAN>>
<<LEARNING_UNIT>>
# Learning Unit: Embeddings
## Decision Lens (use when / don't use when)
- Use when: similarity search
## Mental Model
- vectors
<<END_LEARNING_UNIT>>
<<MEMORY_SNIPPET>>
- bullet 1
- bullet 2
<<END_MEMORY>>
""".strip()

    plan = extract_between(raw, "<<PLAN_MARKDOWN>>", "<<END_PLAN>>")
    learning_unit = extract_learning_unit(raw)
    memory = extract_between(raw, "<<MEMORY_SNIPPET>>", "<<END_MEMORY>>")

    assert "# Week 1 Learning Plan" in plan
    assert "# Learning Unit: Embeddings" in learning_unit
    assert "- bullet 1" in memory


def test_split_markdown_extracts_chat_bubble_linkedin_template_heading():
    raw = """# Week 1 Learning Plan
Plan content

💬 LinkedIn Post Template
LinkedIn draft content
"""

    plan_markdown, linkedin_markdown = split_markdown_into_plan_and_linkedin(raw)

    assert plan_markdown == "# Week 1 Learning Plan\nPlan content"
    assert linkedin_markdown.rstrip() == "💬 LinkedIn Post Template\nLinkedIn draft content"


def test_split_markdown_extracts_plain_linkedin_draft_heading():
    raw = """# Week 1 Learning Plan
Plan content

LinkedIn Post Draft
LinkedIn draft content
"""

    plan_markdown, linkedin_markdown = split_markdown_into_plan_and_linkedin(raw)

    assert plan_markdown == "# Week 1 Learning Plan\nPlan content"
    assert linkedin_markdown.rstrip() == "LinkedIn Post Draft\nLinkedIn draft content"


def test_split_markdown_excludes_files_to_generate_from_linkedin_section():
    raw = """# Week 1 Learning Plan
Plan content

💬 LinkedIn Post Template
LinkedIn draft content

📂 Files to Generate
- /weekly_plans/week_1_plan.md
- /posts/linkedin_week_1.md
"""

    plan_markdown, linkedin_markdown = split_markdown_into_plan_and_linkedin(raw)

    assert plan_markdown == "# Week 1 Learning Plan\nPlan content"
    assert linkedin_markdown == "💬 LinkedIn Post Template\nLinkedIn draft content"
    assert "Files to Generate" not in linkedin_markdown


def test_week_heading_enforcement():
    raw = "# Week 3 Learning Plan\nContent"
    enforced = enforce_week_heading(raw, week_number=1)
    assert enforced.splitlines()[0] == "# Week 1 Learning Plan"
