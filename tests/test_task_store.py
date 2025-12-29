"""Tests for task_store utilities."""

from pathlib import Path

import pytest

# Ensure project root is on sys.path for module imports.
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.task_store import (
    load_tasks,
    select_quiz_tasks,
    update_tasks_from_quiz_results,
    upsert_tasks_from_plan,
)


def test_upsert_tasks_from_plan_creates_tasks(tmp_path: Path):
    plan_md = (PROJECT_ROOT / "tests" / "fixtures" / "sample_plan.md").read_text(encoding="utf-8")
    tasks_path = tmp_path / "tasks.csv"

    created, updated = upsert_tasks_from_plan(
        plan_md=plan_md,
        tasks_path=tasks_path,
        source_week="2025-01-05",
        default_priority=3,
    )

    tasks = load_tasks(tasks_path)
    titles = [task.get("title") for task in tasks]

    assert created == 3
    assert updated == 0
    assert "Understand embeddings basics" in titles
    assert "Build a simple vector index" in titles
    assert "Write retrieval notes" in titles


def test_update_tasks_from_quiz_results_rolling_avg_and_propose(tmp_path: Path):
    fixture = PROJECT_ROOT / "tests" / "fixtures" / "sample_tasks.csv"
    tasks_path = tmp_path / "tasks.csv"
    tasks_path.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")

    updated, propose_done = update_tasks_from_quiz_results(
        tasks_path=tasks_path,
        quiz_results=[
            {
                "task_id": "task-1",
                "score": 0.9,
                "notes": "Strong recall",
                "timestamp": "2025-01-03T00:00:00+00:00",
            }
        ],
        auto_close=False,
    )

    tasks = load_tasks(tasks_path)
    task = tasks[0]

    assert updated == 1
    assert pytest.approx(task.get("evidence_score"), 0.001) == 0.75
    assert task.get("evidence_count") == 2
    assert task.get("status") == "IN_PROGRESS"
    assert "task-1" in propose_done


def test_select_quiz_tasks_prioritizes_needs_review(tmp_path: Path):
    tasks_path = tmp_path / "tasks.csv"
    tasks_path.write_text(
        "\n".join(
            [
                "task_id,created_at,updated_at,status,source_week,title,topic,estimated_minutes,priority,prerequisites,evidence_score,evidence_count,last_evaluated_at,notes",
                "task-a,2025-01-01T00:00:00+00:00,2025-01-02T00:00:00+00:00,NEEDS_REVIEW,2025-01-02,Review embeddings,embeddings,15,3,,0.9,1,,",
                "task-b,2025-01-01T00:00:00+00:00,2025-01-01T00:00:00+00:00,IN_PROGRESS,2025-01-02,Implement index,vector search,20,2,,0.1,1,,",
                "task-c,2025-01-01T00:00:00+00:00,2025-01-01T00:00:00+00:00,TODO,2025-01-02,Write notes,writing,10,1,,0.2,0,,",
            ]
        ),
        encoding="utf-8",
    )

    selected = select_quiz_tasks(tasks_path, n=3)
    ids = [task.get("task_id") for task in selected]

    assert ids[0] == "task-a"
    assert ids[1] == "task-b"
