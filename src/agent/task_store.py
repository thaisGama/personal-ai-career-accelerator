"""CSV-backed task tracking helpers for the weekly planner + quiz loop."""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from uuid import uuid4

TASKS_HEADER = [
    "task_id",
    "created_at",
    "updated_at",
    "status",
    "source_week",
    "title",
    "topic",
    "estimated_minutes",
    "priority",
    "prerequisites",
    "evidence_score",
    "evidence_count",
    "last_evaluated_at",
    "notes",
]

OPEN_STATUSES = {"TODO", "IN_PROGRESS", "NEEDS_REVIEW"}
STATUS_ORDER = {"NEEDS_REVIEW": 0, "IN_PROGRESS": 1, "TODO": 2, "BLOCKED": 3, "DONE": 4}
PRIORITY_EMOJI = {"🔥": 1, "⭐": 2, "🌱": 3}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_int(value: str | None) -> Optional[int]:
    if value is None:
        return None
    value = str(value).strip()
    return int(value) if value else None


def _parse_float(value: str | None) -> Optional[float]:
    if value is None:
        return None
    value = str(value).strip()
    return float(value) if value else None


def _parse_datetime(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _ensure_tasks_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(TASKS_HEADER)


def load_tasks(path: Path) -> List[Dict[str, object]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        tasks: List[Dict[str, object]] = []
        for row in reader:
            tasks.append(
                {
                    "task_id": row.get("task_id", ""),
                    "created_at": row.get("created_at", ""),
                    "updated_at": row.get("updated_at", ""),
                    "status": row.get("status", "TODO"),
                    "source_week": row.get("source_week", ""),
                    "title": row.get("title", ""),
                    "topic": row.get("topic", ""),
                    "estimated_minutes": _parse_int(row.get("estimated_minutes")),
                    "priority": _parse_int(row.get("priority")) or 3,
                    "prerequisites": row.get("prerequisites", ""),
                    "evidence_score": _parse_float(row.get("evidence_score")) or 0.0,
                    "evidence_count": _parse_int(row.get("evidence_count")) or 0,
                    "last_evaluated_at": row.get("last_evaluated_at", ""),
                    "notes": row.get("notes", ""),
                }
            )
        return tasks


def save_tasks(path: Path, tasks: Iterable[Dict[str, object]]) -> None:
    _ensure_tasks_file(path)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TASKS_HEADER)
        writer.writeheader()
        for task in tasks:
            writer.writerow(
                {
                    "task_id": task.get("task_id", ""),
                    "created_at": task.get("created_at", ""),
                    "updated_at": task.get("updated_at", ""),
                    "status": task.get("status", "TODO"),
                    "source_week": task.get("source_week", ""),
                    "title": task.get("title", ""),
                    "topic": task.get("topic", ""),
                    "estimated_minutes": task.get("estimated_minutes") or "",
                    "priority": task.get("priority") or "",
                    "prerequisites": task.get("prerequisites", ""),
                    "evidence_score": f"{task.get('evidence_score', 0.0):.3f}",
                    "evidence_count": task.get("evidence_count", 0),
                    "last_evaluated_at": task.get("last_evaluated_at", ""),
                    "notes": task.get("notes", ""),
                }
            )


def _normalize_title(text: str) -> str:
    text = re.sub(r"[^a-z0-9\s]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _infer_topic(title: str) -> str:
    lowered = title.lower()
    if "embedding" in lowered:
        return "embeddings"
    if "vector" in lowered:
        return "vector search"
    if "retrieval" in lowered or "rag" in lowered:
        return "retrieval"
    if "agent" in lowered:
        return "agents"
    if "prompt" in lowered:
        return "prompting"
    if "eval" in lowered:
        return "evaluation"
    if "llm" in lowered:
        return "llm"
    return ""


def _extract_micro_task_lines(plan_md: str) -> List[str]:
    lines = plan_md.splitlines()
    in_section = False
    results: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if "micro tasks" in lowered:
            in_section = True
            continue
        if in_section:
            if stripped.startswith(("#", "🧪", "💬", "📂")) and "micro tasks" not in lowered:
                break
            if line.lstrip() != line:
                continue
            if stripped.startswith(("-", "•")) or stripped.lower().startswith("task "):
                results.append(stripped)
    return results


def _parse_task_line(line: str, default_priority: int) -> Tuple[str, Optional[int], int]:
    minutes = None
    minutes_match = re.search(r"(\d+)\s*min", line, flags=re.IGNORECASE)
    if minutes_match:
        minutes = int(minutes_match.group(1))
    priority = default_priority
    for emoji, value in PRIORITY_EMOJI.items():
        if emoji in line:
            priority = value
            break
    clean = line.lstrip("-• ").strip()
    clean = clean.replace("**", "")
    task_title = clean
    task_match = re.search(r"task\s*\d+[^:]*:\s*(.+)", clean, flags=re.IGNORECASE)
    if task_match:
        task_title = task_match.group(1).strip()
    elif ":" in clean:
        task_title = clean.split(":", 1)[-1].strip()
    task_title = re.sub(r"\s*\((\d+)\s*min\)\s*", " ", task_title, flags=re.IGNORECASE).strip()
    return task_title, minutes, priority


def upsert_tasks_from_plan(
    plan_md: str,
    tasks_path: Path,
    source_week: str,
    default_priority: int = 3,
) -> Tuple[int, int]:
    tasks = load_tasks(tasks_path)
    now_iso = _utc_now_iso()
    micro_task_lines = _extract_micro_task_lines(plan_md)
    created = 0
    updated = 0

    for line in micro_task_lines:
        title, estimated_minutes, priority = _parse_task_line(line, default_priority)
        if not title:
            continue
        topic = _infer_topic(title)
        norm_key = (_normalize_title(title), _normalize_title(topic))
        matched = None
        for task in tasks:
            if task.get("status") == "DONE":
                continue
            existing_key = (
                _normalize_title(str(task.get("title", ""))),
                _normalize_title(str(task.get("topic", ""))),
            )
            if existing_key == norm_key:
                matched = task
                break
        if matched:
            matched["updated_at"] = now_iso
            matched["source_week"] = source_week
            if estimated_minutes:
                matched["estimated_minutes"] = estimated_minutes
            matched["priority"] = priority
            updated += 1
            continue

        task = {
            "task_id": str(uuid4()),
            "created_at": now_iso,
            "updated_at": now_iso,
            "status": "TODO",
            "source_week": source_week,
            "title": title,
            "topic": topic,
            "estimated_minutes": estimated_minutes,
            "priority": priority,
            "prerequisites": "",
            "evidence_score": 0.0,
            "evidence_count": 0,
            "last_evaluated_at": "",
            "notes": "",
        }
        tasks.append(task)
        created += 1

    save_tasks(tasks_path, tasks)
    return created, updated


def _sort_key_for_task(task: Dict[str, object]) -> Tuple[int, int, float, datetime]:
    status = str(task.get("status", "TODO"))
    status_rank = STATUS_ORDER.get(status, 99)
    priority = int(task.get("priority") or 3)
    evidence_score = float(task.get("evidence_score") or 0.0)
    updated_at = _parse_datetime(str(task.get("updated_at") or "")) or datetime(1970, 1, 1)
    return status_rank, priority, evidence_score, updated_at


def select_quiz_tasks(tasks_path: Path, n: int = 3) -> List[Dict[str, object]]:
    tasks = load_tasks(tasks_path)
    candidates = [task for task in tasks if task.get("status") in OPEN_STATUSES]
    sorted_tasks = sorted(candidates, key=_sort_key_for_task)
    return [
        {
            "task_id": task.get("task_id", ""),
            "title": task.get("title", ""),
            "topic": task.get("topic", ""),
            "status": task.get("status", ""),
            "priority": task.get("priority", 3),
            "evidence_score": task.get("evidence_score", 0.0),
        }
        for task in sorted_tasks[:n]
    ]


def update_tasks_from_quiz_results(
    tasks_path: Path,
    quiz_results: List[Dict[str, object]],
    auto_close: bool = False,
) -> Tuple[int, List[str]]:
    tasks = load_tasks(tasks_path)
    tasks_by_id = {task.get("task_id"): task for task in tasks}
    propose_done: List[str] = []
    updated = 0

    for result in quiz_results:
        task_id = result.get("task_id")
        if not task_id or task_id not in tasks_by_id:
            continue
        task = tasks_by_id[task_id]
        score = float(result.get("score") or 0.0)
        now_count = int(task.get("evidence_count") or 0)
        prev_score = float(task.get("evidence_score") or 0.0)
        new_score = (prev_score * now_count + score) / (now_count + 1)

        task["evidence_count"] = now_count + 1
        task["evidence_score"] = new_score
        task["last_evaluated_at"] = result.get("timestamp") or _utc_now_iso()
        task["updated_at"] = _utc_now_iso()

        if score < 0.5:
            task["status"] = "NEEDS_REVIEW"
        elif score < 0.8:
            task["status"] = "IN_PROGRESS"
        else:
            if task["evidence_count"] >= 2:
                if auto_close:
                    task["status"] = "DONE"
                else:
                    task["status"] = "IN_PROGRESS"
                    propose_done.append(str(task_id))
            else:
                task["status"] = "IN_PROGRESS"

        notes = result.get("notes")
        if notes:
            existing = str(task.get("notes") or "")
            task["notes"] = f"{existing} | {notes}".strip(" |")
        updated += 1

    save_tasks(tasks_path, tasks)
    return updated, propose_done


def mark_tasks_done(tasks_path: Path, task_ids: Iterable[str]) -> int:
    tasks = load_tasks(tasks_path)
    target = set(task_ids)
    updated = 0
    now_iso = _utc_now_iso()
    for task in tasks:
        if task.get("task_id") in target:
            task["status"] = "DONE"
            task["updated_at"] = now_iso
            updated += 1
    save_tasks(tasks_path, tasks)
    return updated


@dataclass
class TaskProgressSummary:
    counts_by_status: Dict[str, int]
    open_tasks: List[Dict[str, object]]
    weak_topics: List[str]
    completed_last_week: List[str]


def summarize_task_progress(tasks_path: Path) -> TaskProgressSummary:
    tasks = load_tasks(tasks_path)
    counts: Dict[str, int] = defaultdict(int)
    for task in tasks:
        counts[str(task.get("status", "TODO"))] += 1

    open_tasks = select_quiz_tasks(tasks_path, n=5)

    topic_scores: Dict[str, List[float]] = defaultdict(list)
    for task in tasks:
        topic = str(task.get("topic") or "").strip()
        if not topic:
            continue
        topic_scores[topic].append(float(task.get("evidence_score") or 0.0))

    averaged_topics = []
    for topic, scores in topic_scores.items():
        avg_score = sum(scores) / max(len(scores), 1)
        averaged_topics.append((avg_score, topic))
    weak_topics = [topic for _, topic in sorted(averaged_topics, key=lambda item: item[0])[:3]]

    completed_last_week: List[str] = []
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    for task in tasks:
        if task.get("status") != "DONE":
            continue
        updated_at = _parse_datetime(str(task.get("updated_at") or ""))
        if updated_at and updated_at >= week_ago:
            completed_last_week.append(str(task.get("title") or ""))

    return TaskProgressSummary(
        counts_by_status=dict(counts),
        open_tasks=open_tasks,
        weak_topics=weak_topics,
        completed_last_week=completed_last_week,
    )
