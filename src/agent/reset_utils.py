"""Helpers for resolving reset paths and scopes."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List


def resolve_tasks_path(base_dir: Path) -> Path:
    primary = base_dir / "data" / "tasks.csv"
    if primary.exists():
        return primary
    legacy = base_dir / "src" / "agent" / "data" / "tasks.csv"
    return legacy if legacy.exists() else primary


def resolve_learning_progress_path(base_dir: Path) -> Path:
    return base_dir / "data" / "learning_progress.json"


def resolve_reset_paths(base_dir: Path) -> Dict[str, object]:
    data_dir = base_dir / "data"
    return {
        "tasks_path": resolve_tasks_path(base_dir),
        "learning_progress_path": resolve_learning_progress_path(base_dir),
        "memory_path": base_dir / "docs" / "memory.md",
        "memory_vectors_path": data_dir / "memory_vectors.json",
        "quiz_paths": [
            data_dir / "quiz_results.jsonl",
            data_dir / "quiz_results.csv",
            data_dir / "quiz_results.json",
        ],
        "outputs_dirs": [
            base_dir / "weekly_plans",
            base_dir / "posts",
            base_dir / "docs" / "learning_units",
        ],
    }
