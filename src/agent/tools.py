"""Tool functions for the weekly planner agent."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Tuple
from uuid import uuid4

from .memory.vector_store import LocalVectorStore
from .weekly_planner import (
    append_memory_snippet,
    call_llm,
    extract_between,
    generate_weekly_plan_and_learning_unit,
    save_week_files,
)
from .task_store import (
    TaskProgressSummary,
    load_tasks,
    mark_tasks_done,
    save_tasks,
    select_quiz_tasks,
    summarize_task_progress,
    update_tasks_from_quiz_results,
    upsert_tasks_from_plan,
)


def tool_retrieve_memory(
    goal: str,
    preferences: Dict[str, Any],
    store: LocalVectorStore,
    k: int = 8,
) -> Dict[str, Any]:
    """Retrieve relevant memory snippets for the goal and preferences."""
    pref_text = preferences.get("text", "")
    query_text = f"{goal}\npreferences: {pref_text}".strip()

    try:
        results = store.search(query_text, top_k=k)
    except Exception:
        results = []

    memory_hits = []
    if results:
        snippets = []
        for score, item in results:
            snippets.append(f"- (score={score:.3f}) {item.text.strip()}")
            memory_hits.append({"id": item.id, "text": item.text, "score": score})
        memory_context = (
            "Top relevant notes from past weeks (semantic search):\n"
            + "\n".join(snippets)
            + "\n"
        )
        memory_used = True
    else:
        memory_context = ""
        memory_used = False

    return {
        "memory_context": memory_context,
        "memory_hits": memory_hits,
        "audit": {
            "memory_used": memory_used,
            "memory_snippets_count": len(memory_hits),
        },
    }


def tool_generate_weekly_plan(
    goal: str,
    hours_per_week: float,
    max_session_minutes: int,
    preferences: Dict[str, Any],
    memory_context: str,
    audit: Dict[str, Any],
    model: str,
    base_dir: Path,
    task_progress: TaskProgressSummary | Dict[str, Any] | None = None,
    roadmap: Dict[str, Any] | None = None,
    roadmap_path: str | None = None,
    roadmap_id: str | None = None,
) -> Dict[str, Any]:
    """Generate the weekly plan markdown via the LLM."""
    preferences_text = preferences.get("text")
    target_level = preferences.get("target_level") or "medium"
    background = preferences.get("background") or ""
    memory_context_prompt = (
        memory_context
        if memory_context.strip()
        else "There is no relevant past memory yet. Plan as if this is the first week.\n"
    )
    memory_used = bool(audit.get("memory_used"))
    memory_source = (Path(base_dir) / "data" / "memory_vectors.json").as_posix()
    memory_char_count = len(memory_context) if memory_used else 0

    if task_progress and not isinstance(task_progress, TaskProgressSummary):
        task_progress = TaskProgressSummary(
            counts_by_status=task_progress.get("counts_by_status", {}),
            open_tasks=task_progress.get("open_tasks", []),
            weak_topics=task_progress.get("weak_topics", []),
            completed_last_week=task_progress.get("completed_last_week", []),
        )

    roadmap_context = None
    roadmap_progress = None
    roadmap_meta: Dict[str, Any] | None = None
    week_number = None
    if roadmap:
        effective_roadmap_id = _infer_roadmap_id(goal, roadmap_id, roadmap_path)
        tasks_path = Path(base_dir) / "data" / "tasks.csv"
        tasks = load_tasks(tasks_path)
        progress = _compute_roadmap_progress(roadmap, tasks, hours_per_week, effective_roadmap_id)
        roadmap_context = _format_roadmap_context(roadmap, progress)
        roadmap_progress = _format_roadmap_progress(roadmap, progress)
        week_number = progress.get("week_number")
        milestone_task_counts = progress.get("milestone_task_counts", {})
        sorted_milestones = dict(sorted(milestone_task_counts.items(), key=lambda item: item[0])[:10])
        roadmap_meta = {
            "roadmap_path": roadmap_path or "",
            "roadmap_id": effective_roadmap_id,
            "topic": roadmap.get("topic"),
            "target_level": roadmap.get("target_level"),
            "total_estimated_hours": roadmap.get("total_estimated_hours"),
            "estimated_weeks_at_hours_per_week": roadmap.get("estimated_weeks_at_hours_per_week"),
            "phase_count": len(roadmap.get("phases", [])),
            "current_phase": progress.get("current_phase_id"),
            "current_milestone": progress.get("current_milestone_id"),
            "remaining_hours": progress.get("remaining_hours"),
            "week_number": progress.get("week_number"),
            "completed_hours": progress.get("completed_hours"),
            "completed_milestones": progress.get("completed_milestones"),
            "computed_week_number": progress.get("computed_week_number"),
            "milestone_task_counts": sorted_milestones,
            "milestone_completion_mode": progress.get("milestone_completion_mode"),
            "used_hours_per_week": progress.get("used_hours_per_week"),
            "debug_notes": progress.get("debug_notes"),
        }

    generation = generate_weekly_plan_and_learning_unit(
        goal=goal,
        time_per_week_hours=hours_per_week,
        max_session_minutes=max_session_minutes,
        preferences=preferences_text,
        memory_context=memory_context_prompt,
        memory_used=memory_used,
        memory_source=memory_source,
        memory_char_count=memory_char_count,
        task_progress=task_progress,
        roadmap_context=roadmap_context,
        roadmap_progress=roadmap_progress,
        week_number=week_number,
        target_level=target_level,
        background=background,
        model=model,
    )

    return {
        "weekly_plan_md": generation.get("plan_markdown", ""),
        "linkedin_post_md": generation.get("linkedin_markdown", ""),
        "learning_unit_md": generation.get("learning_unit_md", ""),
        "memory_snippet": generation.get("memory_snippet", "") or "",
        "raw_llm_output": generation.get("raw_plan_output", ""),
        "raw_learning_unit_output": generation.get("raw_learning_unit_output", ""),
        "roadmap_meta": roadmap_meta or {},
    }


def tool_save_outputs(
    base_dir: Path,
    weekly_plan_md: str,
    linkedin_post_md: str,
    memory_snippet: str,
    learning_unit_md: str = "",
    learning_unit_slug_source: str | None = None,
) -> Dict[str, Any]:
    """Save generated artifacts and update memory when available."""
    plan_path, linkedin_path, learning_unit_path = save_week_files(
        plan_markdown=weekly_plan_md,
        linkedin_markdown=linkedin_post_md,
        base_dir=base_dir,
        learning_unit_md=learning_unit_md,
        learning_unit_slug_source=learning_unit_slug_source,
    )

    memory_updated = False
    memory_path = ""
    if memory_snippet and memory_snippet.strip():
        memory_path = append_memory_snippet(memory_snippet, path=Path(base_dir) / "docs" / "memory.md").as_posix()
        memory_updated = True
        try:
            store = LocalVectorStore(path=Path(base_dir) / "data" / "memory_vectors.json")
            store.add(
                text=memory_snippet.strip(),
                meta={"date": date.today().isoformat()},
            )
        except Exception:
            pass

    return {
        "weekly_plan_path": plan_path.as_posix(),
        "linkedin_path": linkedin_path.as_posix(),
        "learning_unit_path": learning_unit_path.as_posix() if learning_unit_path else "",
        "memory_updated": memory_updated,
        "memory_path": memory_path,
    }


def tool_decide_next_task(weekly_plan_md: str, memory_context: str) -> Dict[str, Any]:
    """Pick the next task based on a simple heuristic."""
    _ = memory_context

    def _clean_bullet(text: str) -> str:
        text = text.strip()
        text = text.lstrip("-* ").strip()
        if text.startswith("[ ]"):
            text = text[3:].strip()
        if text.lower().startswith("todo"):
            text = text.split(":", 1)[-1].strip() or text
        return text

    lines = weekly_plan_md.splitlines()
    for idx, line in enumerate(lines):
        if "next actions" in line.strip().lower():
            for candidate in lines[idx + 1 :]:
                cand = candidate.strip()
                if not cand:
                    continue
                if cand.startswith("#"):
                    break
                if cand.lstrip().startswith(("-", "*")):
                    return {"next_task": _clean_bullet(cand)}
            break

    for line in lines:
        if "todo" in line.lower():
            return {"next_task": _clean_bullet(line)}

    return {"next_task": "Review the weekly plan and schedule the first micro-task for this week."}


def _slugify_goal(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or "goal"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _roadmap_paths(goal: str, base_dir: Path, roadmap_id: str | None = None) -> Tuple[Path, Path, Path]:
    fallback_slug = _slugify_goal(goal)
    effective_id = _slugify_goal(roadmap_id) if roadmap_id else fallback_slug
    root = Path(base_dir) / "roadmaps"
    json_path = root / f"{effective_id}_roadmap.json"
    legacy_json_path = root / f"{fallback_slug}_roadmap.json"
    md_path = root / f"{effective_id}_roadmap.md"
    return json_path, legacy_json_path, md_path


def _infer_roadmap_id(goal: str, roadmap_id: str | None, roadmap_path: str | None) -> str:
    if roadmap_id:
        return _slugify_goal(roadmap_id)
    if roadmap_path:
        name = Path(roadmap_path).name
        if name.endswith("_roadmap.json"):
            return name[: -len("_roadmap.json")]
    return _slugify_goal(goal)


def _validate_roadmap_schema(roadmap: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []

    def _expect(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    _expect(isinstance(roadmap, dict), "Roadmap must be a JSON object.")
    if not isinstance(roadmap, dict):
        return False, errors

    _expect(isinstance(roadmap.get("topic"), str), "topic must be a string.")
    _expect(roadmap.get("target_level") in {"light", "medium", "hardcore"}, "target_level invalid.")
    _expect(
        isinstance(roadmap.get("total_estimated_hours"), (int, float)),
        "total_estimated_hours must be a number.",
    )

    weeks = roadmap.get("estimated_weeks_at_hours_per_week")
    _expect(isinstance(weeks, dict), "estimated_weeks_at_hours_per_week must be an object.")
    if isinstance(weeks, dict):
        for key in ("2", "5", "7"):
            _expect(isinstance(weeks.get(key), (int, float)), f"estimated_weeks_at_hours_per_week[{key}] missing.")

    _expect(isinstance(roadmap.get("prerequisites"), list), "prerequisites must be a list.")
    _expect(isinstance(roadmap.get("completion_criteria"), list), "completion_criteria must be a list.")

    phases = roadmap.get("phases")
    _expect(isinstance(phases, list) and phases, "phases must be a non-empty list.")
    if isinstance(phases, list):
        for phase in phases:
            _expect(isinstance(phase, dict), "phase must be an object.")
            if not isinstance(phase, dict):
                continue
            _expect(isinstance(phase.get("phase_id"), str), "phase_id must be a string.")
            _expect(isinstance(phase.get("title"), str), "phase title must be a string.")
            _expect(isinstance(phase.get("estimated_hours"), (int, float)), "phase estimated_hours must be a number.")
            _expect(isinstance(phase.get("outcomes"), list), "phase outcomes must be a list.")
            milestones = phase.get("milestones")
            _expect(isinstance(milestones, list) and milestones, "phase milestones must be a non-empty list.")
            if isinstance(milestones, list):
                for milestone in milestones:
                    _expect(isinstance(milestone, dict), "milestone must be an object.")
                    if not isinstance(milestone, dict):
                        continue
                    _expect(isinstance(milestone.get("milestone_id"), str), "milestone_id must be a string.")
                    _expect(isinstance(milestone.get("title"), str), "milestone title must be a string.")
                    _expect(
                        isinstance(milestone.get("estimated_hours"), (int, float)),
                        "milestone estimated_hours must be a number.",
                    )
                    _expect(isinstance(milestone.get("definition_of_done"), list), "definition_of_done must be a list.")
                    _expect(isinstance(milestone.get("deliverables"), list), "deliverables must be a list.")
                    _expect(
                        milestone.get("depth") in {"intro", "operational"},
                        "milestone depth must be intro|operational.",
                    )
                    _expect(
                        isinstance(milestone.get("suggested_practice"), list),
                        "suggested_practice must be a list.",
                    )
                    resources = milestone.get("resources", [])
                    _expect(isinstance(resources, list), "resources must be a list.")
                    if isinstance(resources, list):
                        _expect(len(resources) <= 2, "resources must have at most 2 items.")
                        for resource in resources:
                            _expect(isinstance(resource, dict), "resource must be an object.")
                            if not isinstance(resource, dict):
                                continue
                            _expect(isinstance(resource.get("title"), str), "resource title must be a string.")
                            _expect(isinstance(resource.get("owner"), str), "resource owner must be a string.")
                            _expect(isinstance(resource.get("platform"), str), "resource platform must be a string.")
                            _expect(
                                isinstance(resource.get("search_phrase"), str),
                                "resource search_phrase must be a string.",
                            )

    return len(errors) == 0, errors


def _render_roadmap_markdown(roadmap: Dict[str, Any]) -> str:
    lines = []
    lines.append(f"# Global Learning Roadmap: {roadmap.get('topic', '')}")
    lines.append("")
    lines.append(f"- Target level: {roadmap.get('target_level', '')}")
    lines.append(f"- Total estimated hours: {roadmap.get('total_estimated_hours', '')}")
    weeks = roadmap.get("estimated_weeks_at_hours_per_week", {})
    lines.append(
        "- Estimated weeks at 2/5/7 hrs per week: "
        f"{weeks.get('2', '?')} / {weeks.get('5', '?')} / {weeks.get('7', '?')}"
    )
    lines.append("")
    prerequisites = roadmap.get("prerequisites") or []
    if prerequisites:
        lines.append("## Prerequisites")
        lines.extend([f"- {item}" for item in prerequisites])
        lines.append("")
    lines.append("## Phases")
    for phase in roadmap.get("phases", []):
        lines.append(f"### {phase.get('phase_id')}: {phase.get('title')}")
        lines.append(f"- Estimated hours: {phase.get('estimated_hours')}")
        outcomes = phase.get("outcomes") or []
        if outcomes:
            lines.append("- Outcomes:")
            lines.extend([f"  - {item}" for item in outcomes])
        lines.append("- Milestones:")
        for milestone in phase.get("milestones", []):
            lines.append(f"  - {milestone.get('milestone_id')}: {milestone.get('title')}")
            lines.append(f"    - Estimated hours: {milestone.get('estimated_hours')}")
            if milestone.get("depth"):
                lines.append(f"    - Depth: {milestone.get('depth')}")
            dod = milestone.get("definition_of_done") or []
            if dod:
                lines.append("    - Definition of done:")
                lines.extend([f"      - {item}" for item in dod])
            deliverables = milestone.get("deliverables") or []
            if deliverables:
                lines.append("    - Deliverables:")
                lines.extend([f"      - {item}" for item in deliverables])
            practice = milestone.get("suggested_practice") or []
            if practice:
                lines.append("    - Suggested practice:")
                lines.extend([f"      - {item}" for item in practice])
            resources = milestone.get("resources") or []
            if resources:
                lines.append("    - Resources:")
                for resource in resources[:2]:
                    title = resource.get("title")
                    owner = resource.get("owner")
                    platform = resource.get("platform")
                    search_phrase = resource.get("search_phrase")
                    lines.append(f"      - {title} - {owner} - {platform} - search: \"{search_phrase}\"")
        lines.append("")
    completion = roadmap.get("completion_criteria") or []
    if completion:
        lines.append("## Completion Criteria")
        lines.extend([f"- {item}" for item in completion])
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _parse_roadmap_tags(title: str) -> Tuple[str | None, str | None]:
    phase_match = re.search(r"\[phase:([^\]]+)\]", title, flags=re.IGNORECASE)
    milestone_match = re.search(r"\[milestone:([^\]]+)\]", title, flags=re.IGNORECASE)
    phase_id = phase_match.group(1).strip() if phase_match else None
    milestone_id = milestone_match.group(1).strip() if milestone_match else None
    return phase_id, milestone_id


def _compute_roadmap_progress(
    roadmap: Dict[str, Any],
    tasks: List[Dict[str, object]],
    hours_per_week: float,
    roadmap_id: str | None = None,
) -> Dict[str, Any]:
    milestones: List[Dict[str, Any]] = []
    milestone_hours: Dict[str, float] = {}
    milestone_phase: Dict[str, str] = {}

    for phase in roadmap.get("phases", []):
        phase_id = str(phase.get("phase_id", "")).strip()
        for milestone in phase.get("milestones", []):
            milestone_id = str(milestone.get("milestone_id", "")).strip()
            if not milestone_id:
                continue
            hours = float(milestone.get("estimated_hours") or 0.0)
            milestones.append(
                {
                    "phase_id": phase_id,
                    "milestone_id": milestone_id,
                    "estimated_hours": hours,
                }
            )
            milestone_hours[milestone_id] = hours
            milestone_phase[milestone_id] = phase_id

    milestone_tasks: Dict[str, List[Dict[str, object]]] = {}
    for task in tasks:
        if roadmap_id:
            task_roadmap_id = str(task.get("roadmap_id") or "")
            if task_roadmap_id and task_roadmap_id != roadmap_id:
                continue
        milestone_id = str(task.get("milestone_id") or "").strip()
        if not milestone_id:
            title = str(task.get("title") or "")
            _, milestone_id = _parse_roadmap_tags(title)
        if not milestone_id:
            continue
        milestone_tasks.setdefault(milestone_id, []).append(task)

    milestone_task_counts: Dict[str, Dict[str, int]] = {}
    for milestone_id, task_list in milestone_tasks.items():
        total = len(task_list)
        done = sum(1 for task in task_list if task.get("status") == "DONE")
        validated = sum(1 for task in task_list if bool(task.get("learning_validated")))
        done_and_validated = sum(
            1
            for task in task_list
            if task.get("status") == "DONE" and bool(task.get("learning_validated"))
        )
        milestone_task_counts[milestone_id] = {
            "total": total,
            "done": done,
            "validated": validated,
            "done_and_validated": done_and_validated,
        }

    completed_milestones: List[str] = []
    for milestone_id, task_list in milestone_tasks.items():
        if not task_list:
            continue
        if all(
            task.get("status") == "DONE" and bool(task.get("learning_validated"))
            for task in task_list
        ):
            # Require quiz validation to advance milestone progress.
            completed_milestones.append(milestone_id)

    completed_hours = sum(milestone_hours.get(mid, 0.0) for mid in completed_milestones)
    total_hours = float(roadmap.get("total_estimated_hours") or 0.0)
    remaining_hours = max(total_hours - completed_hours, 0.0) if total_hours else 0.0

    current_milestone_id = None
    for milestone in milestones:
        if milestone["milestone_id"] not in completed_milestones:
            current_milestone_id = milestone["milestone_id"]
            break

    if not current_milestone_id and milestones:
        current_milestone_id = milestones[-1]["milestone_id"]

    current_phase_id = milestone_phase.get(current_milestone_id or "", "")
    week_number = 1
    if hours_per_week and hours_per_week > 0:
        week_number = int(completed_hours / hours_per_week) + 1

    return {
        "completed_milestones": completed_milestones,
        "completed_hours": completed_hours,
        "remaining_hours": remaining_hours,
        "current_phase_id": current_phase_id,
        "current_milestone_id": current_milestone_id,
        "week_number": week_number,
        "milestone_task_counts": milestone_task_counts,
        "milestone_completion_mode": "DONE+validated gate",
        "used_hours_per_week": hours_per_week,
        "computed_week_number": week_number,
        "debug_notes": "week_number = int(completed_hours/hours_per_week)+1",
    }


def _format_roadmap_context(roadmap: Dict[str, Any], progress: Dict[str, Any]) -> str:
    current_phase_id = progress.get("current_phase_id") or ""
    current_milestone_id = progress.get("current_milestone_id") or ""
    phase_detail = None
    milestone_detail = None
    for phase in roadmap.get("phases", []):
        if str(phase.get("phase_id")) == current_phase_id:
            phase_detail = phase
            for milestone in phase.get("milestones", []):
                if str(milestone.get("milestone_id")) == current_milestone_id:
                    milestone_detail = milestone
            break

    lines = [
        "ROADMAP CONTEXT",
        f"- Topic: {roadmap.get('topic')}",
        f"- Target level: {roadmap.get('target_level')}",
        f"- Total estimated hours: {roadmap.get('total_estimated_hours')}",
        f"- Current phase: {current_phase_id} {phase_detail.get('title') if phase_detail else ''}".strip(),
        f"- Current milestone: {current_milestone_id} {milestone_detail.get('title') if milestone_detail else ''}".strip(),
    ]
    if milestone_detail:
        if milestone_detail.get("depth"):
            lines.append(f"- Milestone depth: {milestone_detail.get('depth')}")
        if milestone_detail.get("definition_of_done"):
            dod = ", ".join(milestone_detail.get("definition_of_done")[:4])
            lines.append(f"- Milestone definition of done: {dod}")
        if milestone_detail.get("deliverables"):
            deliverables = ", ".join(milestone_detail.get("deliverables")[:4])
            lines.append(f"- Milestone deliverables: {deliverables}")
        if milestone_detail.get("suggested_practice"):
            practice = ", ".join(milestone_detail.get("suggested_practice")[:4])
            lines.append(f"- Suggested practice: {practice}")
    lines.append("- Prioritize open tasks tagged to the current milestone when planning.")
    return "\n".join(lines).strip()


def _format_roadmap_progress(roadmap: Dict[str, Any], progress: Dict[str, Any]) -> str:
    weeks = roadmap.get("estimated_weeks_at_hours_per_week") or {}
    return "\n".join(
        [
            "ROADMAP PROGRESS",
            f"- Roadmap: {roadmap.get('topic')} | Target level: {roadmap.get('target_level')}",
            f"- Total estimate: {roadmap.get('total_estimated_hours')} hours | "
            f"Duration @2h/week: {weeks.get('2', '?')} weeks",
            f"- Current focus: Phase {progress.get('current_phase_id')}, Milestone {progress.get('current_milestone_id')}",
            f"- Week number (approx): {progress.get('week_number')}",
            f"- Remaining: {progress.get('remaining_hours')} hours",
        ]
    )


def _seed_roadmap_tasks(roadmap: Dict[str, Any], base_dir: Path, roadmap_id: str) -> int:
    tasks_path = Path(base_dir) / "data" / "tasks.csv"
    tasks = load_tasks(tasks_path)
    existing = {
        (str(task.get("roadmap_id") or ""), str(task.get("milestone_id") or ""))
        for task in tasks
        if task.get("milestone_id")
    }
    now_iso = date.today().isoformat()
    created = 0
    for phase in roadmap.get("phases", []):
        phase_id = str(phase.get("phase_id") or "").strip()
        for milestone in phase.get("milestones", []):
            milestone_id = str(milestone.get("milestone_id") or "").strip()
            if not milestone_id:
                continue
            key = (roadmap_id, milestone_id)
            if key in existing:
                continue
            est_hours = float(milestone.get("estimated_hours") or 0.0)
            est_minutes = int(est_hours * 60) if est_hours else 60
            if est_minutes < 60:
                est_minutes = 60
            tasks.append(
                {
                    "task_id": str(uuid4()),
                    "created_at": _utc_now_iso(),
                    "updated_at": _utc_now_iso(),
                    "status": "TODO",
                    "source_week": now_iso,
                    "title": f"Milestone: {milestone.get('title')}",
                    "topic": roadmap.get("topic") or "",
                    "estimated_minutes": est_minutes,
                    "priority": 2,
                    "prerequisites": "",
                    "evidence_score": 0.0,
                    "evidence_count": 0,
                    "last_evaluated_at": "",
                    "learning_validated": False,
                    "notes": "",
                    "phase_id": phase_id,
                    "milestone_id": milestone_id,
                    "roadmap_id": roadmap_id,
                }
            )
            created += 1
    if created:
        save_tasks(tasks_path, tasks)
    return created


def tool_load_learning_roadmap(
    goal: str,
    base_dir: Path,
    roadmap_id: str | None = None,
    force_regenerate: bool = False,
) -> Dict[str, Any]:
    """Load a saved roadmap JSON if present."""
    json_path, legacy_json_path, _ = _roadmap_paths(goal, base_dir, roadmap_id)
    target_path = json_path if json_path.exists() else legacy_json_path
    if not target_path.exists():
        return {"exists": False}
    if force_regenerate:
        return {"exists": False, "path": target_path.as_posix(), "force_regenerate": True}
    try:
        roadmap = json.loads(target_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"exists": True, "error": f"Failed to parse roadmap JSON: {exc}", "path": target_path.as_posix()}
    return {"exists": True, "roadmap": roadmap, "path": target_path.as_posix()}


def tool_generate_learning_roadmap(
    goal: str,
    target_level: str,
    background: str | None,
    roadmap_id: str | None,
    base_dir: Path,
    model: str,
) -> Dict[str, Any]:
    """Generate and save a multi-week learning roadmap for the goal."""
    if target_level not in {"light", "medium", "hardcore"}:
        target_level = "medium"
    system_prompt = (
        "You are a senior curriculum designer for modern AI Engineers. Create a structured learning roadmap.\n"
        "Return ONLY strict JSON wrapped between the tags:\n"
        "<<ROADMAP_JSON>>\n{...}\n<<END_ROADMAP_JSON>>\n"
        "No extra text before or after the tags.\n"
        "The roadmap must include hands-on deliverables and practice items.\n"
        "MANDATORY AI ENGINEER SPINE (must appear as milestones across phases):\n"
        "- Foundations: LLM mental models and prompt/tool fundamentals\n"
        "- Embeddings and similarity search\n"
        "- Vector search + index tuning\n"
        "- Chunking strategies + document preparation\n"
        "- RAG pipelines (retrieval + grounding)\n"
        "- RAG evaluation (quality, latency, regressions)\n"
        "- Agents and tool use (planning, tool routing, guardrails)\n"
        "- Production concerns (latency, cost, monitoring, safety)\n"
        "- Portfolio project (end-to-end AI engineer artifact)\n"
        "RESOURCE POLICY FOR ROADMAPS\n"
        "- Milestones and suggested practice must NOT depend on paid resources.\n"
        "- Prefer:\n"
        "  - agent-generated explanations and exercises\n"
        "  - free, named online resources (docs, blogs, open-source tutorials)\n"
        "- If a paid resource (book/course) is mentioned:\n"
        "  - it must be explicitly labeled as OPTIONAL\n"
        "  - it must not be required to satisfy any definition_of_done\n"
        "Use realistic hour estimates and keep the scope professional and complete."
    )
    user_prompt = (
        f"Goal: {goal}\n"
        f"Target intensity: {target_level}\n"
        f"Background/constraints: {background or 'none'}\n\n"
        "Milestone resources rules:\n"
        "- Include 0-2 optional FREE resources per milestone.\n"
        "- Each resource must include title, owner, platform, and a search_phrase.\n"
        "- Avoid generic titles like \"Beginner's guide to AI\".\n\n"
        "Return JSON that matches this exact schema:\n"
        "{\n"
        '  "topic": "string",\n'
        '  "target_level": "light|medium|hardcore",\n'
        '  "total_estimated_hours": number,\n'
        '  "estimated_weeks_at_hours_per_week": { "2": number, "5": number, "7": number },\n'
        '  "prerequisites": ["string", ...],\n'
        '  "phases": [\n'
        "    {\n"
        '      "phase_id": "P1",\n'
        '      "title": "string",\n'
        '      "estimated_hours": number,\n'
        '      "outcomes": ["string", ...],\n'
        '      "milestones": [\n'
        "        {\n"
        '          "milestone_id": "M1.1",\n'
        '          "title": "string",\n'
        '          "estimated_hours": number,\n'
        '          "definition_of_done": ["string", ...],\n'
        '          "deliverables": ["string", ...],\n'
        '          "depth": "intro|operational",\n'
        '          "suggested_practice": ["string", ...],\n'
        '          "resources": [\n'
        "            {\n"
        '              "title": "string",\n'
        '              "owner": "string",\n'
        '              "platform": "string",\n'
        '              "search_phrase": "string"\n'
        "            }\n"
        "          ]\n"
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ],\n"
        '  "completion_criteria": ["string", ...]\n'
        "}"
    )

    try:
        raw_output = call_llm(system_prompt=system_prompt, user_prompt=user_prompt, model=model)
    except Exception as exc:
        return {"error": f"Failed to generate roadmap: {exc}"}

    raw_text = raw_output.strip()
    if "<<ROADMAP_JSON>>" in raw_text and "<<END_ROADMAP_JSON>>" in raw_text:
        raw_text = extract_between(raw_text, "<<ROADMAP_JSON>>", "<<END_ROADMAP_JSON>>")
    try:
        roadmap = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return {"error": f"Failed to parse roadmap JSON: {exc}", "raw_output": raw_output}

    valid, errors = _validate_roadmap_schema(roadmap)
    if not valid:
        return {"error": "Roadmap JSON failed schema validation.", "validation_errors": errors, "raw_output": raw_output}

    json_path, _, md_path = _roadmap_paths(goal, base_dir, roadmap_id)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(roadmap, ensure_ascii=True, indent=2), encoding="utf-8")
    md_path.write_text(_render_roadmap_markdown(roadmap), encoding="utf-8")

    effective_id = _slugify_goal(roadmap_id) if roadmap_id else _slugify_goal(goal)
    seeded = _seed_roadmap_tasks(roadmap, base_dir, effective_id)
    return {
        "roadmap": roadmap,
        "roadmap_id": effective_id,
        "path": json_path.as_posix(),
        "markdown_path": md_path.as_posix(),
        "seeded_tasks": seeded,
    }


def tool_load_tasks(path: Path) -> Dict[str, Any]:
    """Load tasks from tasks.csv. Returns empty list if missing."""
    tasks = load_tasks(path)
    return {"tasks": tasks, "tasks_path": path.as_posix()}


def tool_upsert_tasks_from_plan(
    plan_md: str,
    tasks_path: Path,
    source_week: str,
    default_priority: int = 3,
    roadmap_id: str | None = None,
) -> Dict[str, Any]:
    created, updated = upsert_tasks_from_plan(
        plan_md=plan_md,
        tasks_path=tasks_path,
        source_week=source_week,
        default_priority=default_priority,
        roadmap_id=roadmap_id,
    )
    return {"created_count": created, "updated_count": updated, "tasks_path": tasks_path.as_posix()}


def tool_select_quiz_tasks(
    tasks_path: Path, n: int = 3, strategy: str = "priority+weakness", roadmap_id: str | None = None
) -> Dict[str, Any]:
    _ = strategy
    tasks = select_quiz_tasks(tasks_path, n=n, roadmap_id=roadmap_id)
    return {"selected_tasks": tasks, "tasks_path": tasks_path.as_posix()}


def tool_update_tasks_from_quiz_results(
    tasks_path: Path,
    quiz_results: List[Dict[str, Any]],
    auto_close: bool = False,
) -> Dict[str, Any]:
    updated, propose_done = update_tasks_from_quiz_results(
        tasks_path=tasks_path,
        quiz_results=quiz_results,
        auto_close=auto_close,
    )
    return {
        "updated_count": updated,
        "propose_done": propose_done,
        "tasks_path": tasks_path.as_posix(),
    }


def tool_summarize_task_progress(tasks_path: Path) -> Dict[str, Any]:
    summary = summarize_task_progress(tasks_path)
    return {
        "counts_by_status": summary.counts_by_status,
        "open_tasks": summary.open_tasks,
        "weak_topics": summary.weak_topics,
        "completed_last_week": summary.completed_last_week,
        "tasks_path": tasks_path.as_posix(),
    }


def tool_mark_done(tasks_path: Path, task_ids: List[str]) -> Dict[str, Any]:
    updated = mark_tasks_done(tasks_path, task_ids)
    return {"updated_count": updated, "tasks_path": tasks_path.as_posix()}
