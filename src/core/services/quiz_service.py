"""Quiz orchestration helpers decoupled from Streamlit UI."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import src.agent.learning_check as learning_check
from src.agent.tools import tool_load_tasks, tool_update_tasks_from_quiz_results


def generate_quiz_service(
    *,
    topic: str,
    context_text: Optional[str],
    tasks: Optional[list[dict]],
    model: str,
    base_dir: Path,
) -> Dict[str, object]:
    """Generate a micro-quiz and persist it via the learning_check module."""
    return learning_check.generate_micro_quiz(
        topic=topic,
        context_text=context_text,
        tasks=tasks if tasks else None,
        model=model,
        base_dir=base_dir,
    )


def evaluate_quiz_service(
    *,
    topic: str,
    quiz_markdown: str,
    learner_answers: str,
    model: str,
) -> Dict[str, Any]:
    """Evaluate quiz answers via the learning_check module."""
    return learning_check.evaluate_micro_quiz(
        topic=topic,
        quiz_markdown=quiz_markdown,
        learner_answers=learner_answers,
        model=model,
    )


def _build_quiz_results(task_ids: Iterable[str], eval_result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    score = eval_result.get("score") or 0.0
    score_ratio = float(score) / 10.0
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    mastery = eval_result.get("mastery")
    move_on_decision = eval_result.get("move_on_decision")

    quiz_results: List[Dict[str, Any]] = []
    for task_id in task_ids:
        quiz_results.append(
            {
                "task_id": task_id,
                "score": score_ratio,
                "notes": f"quiz_score={score_ratio:.2f} mastery={mastery}",
                "timestamp": timestamp,
                "mastery": mastery,
                "move_on_decision": move_on_decision,
            }
        )
    return quiz_results


def update_tasks_from_quiz_service(
    *,
    task_ids: list[str],
    eval_result: Mapping[str, Any],
    tasks_path: Path,
    auto_close: bool = False,
) -> Dict[str, Any]:
    """Update tasks based on quiz evaluation results and return a UI-friendly summary."""
    if not task_ids:
        return {
            "update_result": {},
            "propose_done": [],
            "statuses": [],
            "quiz_results": [],
        }

    quiz_results = _build_quiz_results(task_ids, eval_result)
    update_result = tool_update_tasks_from_quiz_results(
        tasks_path=tasks_path,
        quiz_results=quiz_results,
        auto_close=auto_close,
    )
    propose_done = update_result.get("propose_done", [])

    tasks_payload = tool_load_tasks(path=tasks_path)
    status_map = {
        task.get("task_id"): task.get("status")
        for task in tasks_payload.get("tasks", [])
        if isinstance(task, dict)
    }
    statuses = [(task_id, status_map.get(task_id, "UNKNOWN")) for task_id in task_ids]

    return {
        "update_result": update_result,
        "propose_done": propose_done,
        "statuses": statuses,
        "quiz_results": quiz_results,
    }


__all__ = [
    "generate_quiz_service",
    "evaluate_quiz_service",
    "update_tasks_from_quiz_service",
]
