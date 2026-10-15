"""Quiz orchestration helpers decoupled from Streamlit UI."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional
from uuid import uuid4

import src.agent.learning_check as learning_check
from src.agent.tools import tool_load_tasks, tool_update_tasks_from_quiz_results
from src.agent import tools
from src.core.io.quiz_results_store import append_quiz_results
from src.core.services.roadmap_context import read_progress, resolve_quiz_day, saved_resource


def _bound_day(base_dir: Path, identity: dict) -> dict:
    weeks, error = read_progress(base_dir)
    if error:
        raise ValueError(error)
    context, error = resolve_quiz_day(weeks, identity.get("roadmap_id"), identity)
    if error or context is None:
        raise ValueError(error or "Quiz day association is unavailable.")
    return context


def generate_day_quiz_service(*, identity: dict, model: str, base_dir: Path) -> Dict[str, object]:
    """Reuse day generation and retain identity plus the exact generated content."""
    context = _bound_day(base_dir, identity)
    quiz_id = str(uuid4())
    generated = tools.tool_generate_quiz_for_day(day_id=identity["day_id"], base_dir=base_dir, model=model, quiz_id=quiz_id)
    path = saved_resource(base_dir, generated.get("quiz_path"), "docs/quizzes")
    if path is None:
        raise ValueError("The generated day quiz could not be found.")
    markdown = path.read_text(encoding="utf-8")
    binding = {**identity, "topic": context["day"]["topic"], "quiz_path": generated["quiz_path"],
               "quiz_id": quiz_id, "quiz_sha256": sha256(markdown.encode()).hexdigest()}
    return {"quiz_markdown": markdown, "quiz_path": str(path), "binding": binding}


def evaluate_day_quiz_service(*, binding: dict, quiz_markdown: str, learner_answers: str,
                              model: str, base_dir: Path) -> Dict[str, Any]:
    """Evaluate the generated quiz snapshot, then append its original identity."""
    _bound_day(base_dir, binding)
    if sha256(quiz_markdown.encode()).hexdigest() != binding.get("quiz_sha256"):
        raise ValueError("Quiz content changed since generation. Generate a new quiz before submitting.")
    result = tools.tool_evaluate_quiz_for_day(
        day_id=binding["day_id"], learner_answers=learner_answers, base_dir=base_dir, model=model,
        quiz_markdown=quiz_markdown, expected_roadmap_id=binding["roadmap_id"], expected_week_id=binding["week_id"],
        quiz_topic=binding["topic"],
    )
    append_quiz_results([{
        **binding, "record_type": "day_quiz", "quiz_result": result["quiz_result"],
        "timestamp": result["completed_at"], "learner_answers": learner_answers,
        "quiz_markdown": quiz_markdown, "evaluation": result["evaluation"],
    }], base_dir=base_dir)
    return result["evaluation"]


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
    "generate_day_quiz_service",
    "evaluate_day_quiz_service",
    "generate_quiz_service",
    "evaluate_quiz_service",
    "update_tasks_from_quiz_service",
]
