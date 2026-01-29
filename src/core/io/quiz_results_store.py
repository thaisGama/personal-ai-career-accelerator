"""Storage helpers for quiz results artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping


def ensure_data_dir(base_dir: Path) -> Path:
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def append_quiz_results(results: Iterable[Mapping[str, object]], base_dir: Path) -> Path:
    """Append quiz result entries to data/quiz_results.jsonl."""
    data_dir = ensure_data_dir(base_dir)
    path = data_dir / "quiz_results.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        for entry in results:
            handle.write(json.dumps(dict(entry), ensure_ascii=True) + "\n")
    return path


__all__ = ["append_quiz_results", "ensure_data_dir"]
