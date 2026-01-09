"""Tests for reset path resolution helpers."""

from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.reset_utils import resolve_reset_paths, resolve_tasks_path


def test_reset_path_resolution_prefers_data_dir(tmp_path: Path):
    data_tasks = tmp_path / "data" / "tasks.csv"
    data_tasks.parent.mkdir(parents=True, exist_ok=True)
    data_tasks.write_text("task_id\n", encoding="utf-8")

    tasks_path = resolve_tasks_path(tmp_path)

    assert tasks_path == data_tasks


def test_reset_path_resolution_falls_back_to_legacy(tmp_path: Path):
    legacy_tasks = tmp_path / "src" / "agent" / "data" / "tasks.csv"
    legacy_tasks.parent.mkdir(parents=True, exist_ok=True)
    legacy_tasks.write_text("task_id\n", encoding="utf-8")

    tasks_path = resolve_tasks_path(tmp_path)

    assert tasks_path == legacy_tasks


def test_reset_paths_handles_missing_files(tmp_path: Path):
    paths = resolve_reset_paths(tmp_path)

    assert paths["tasks_path"].name == "tasks.csv"
    assert paths["memory_path"].name == "memory.md"
