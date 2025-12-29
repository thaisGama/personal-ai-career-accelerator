"""Tool functions for the weekly planner agent."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from .memory.vector_store import LocalVectorStore
from .weekly_planner import (
    append_memory_snippet,
    build_weekly_planner_prompt,
    call_llm,
    extract_between,
    format_weekly_plan,
    save_week_files,
    split_markdown_into_plan_and_linkedin,
)
from .task_store import (
    TaskProgressSummary,
    load_tasks,
    mark_tasks_done,
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
) -> Dict[str, Any]:
    """Generate the weekly plan markdown via the LLM."""
    preferences_text = preferences.get("text")
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

    system_prompt, user_prompt = build_weekly_planner_prompt(
        goal=goal,
        time_per_week_hours=hours_per_week,
        max_session_minutes=max_session_minutes,
        preferences=preferences_text,
        memory_context=memory_context_prompt,
        memory_used=memory_used,
        memory_source=memory_source,
        memory_char_count=memory_char_count,
        task_progress=task_progress,
    )

    raw_markdown = call_llm(system_prompt=system_prompt, user_prompt=user_prompt, model=model)
    memory_audit_block = raw_markdown.split("<<PLAN_MARKDOWN>>", 1)[0].strip()
    plan_text = extract_between(raw_markdown, "<<PLAN_MARKDOWN>>", "<<END_PLAN>>")
    memory_snippet = extract_between(raw_markdown, "<<MEMORY_SNIPPET>>", "<<END_MEMORY>>")

    formatted_markdown = format_weekly_plan(plan_text)
    if memory_audit_block:
        formatted_markdown = f"{memory_audit_block}\n\n{formatted_markdown}"

    plan_markdown, linkedin_markdown = split_markdown_into_plan_and_linkedin(formatted_markdown)

    return {
        "weekly_plan_md": plan_markdown,
        "linkedin_post_md": linkedin_markdown,
        "memory_snippet": memory_snippet or "",
        "raw_llm_output": raw_markdown,
    }


def tool_save_outputs(
    base_dir: Path,
    weekly_plan_md: str,
    linkedin_post_md: str,
    memory_snippet: str,
) -> Dict[str, Any]:
    """Save generated artifacts and update memory when available."""
    plan_path, linkedin_path = save_week_files(
        plan_markdown=weekly_plan_md,
        linkedin_markdown=linkedin_post_md,
        base_dir=base_dir,
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


def tool_load_tasks(path: Path) -> Dict[str, Any]:
    """Load tasks from tasks.csv. Returns empty list if missing."""
    tasks = load_tasks(path)
    return {"tasks": tasks, "tasks_path": path.as_posix()}


def tool_upsert_tasks_from_plan(
    plan_md: str,
    tasks_path: Path,
    source_week: str,
    default_priority: int = 3,
) -> Dict[str, Any]:
    created, updated = upsert_tasks_from_plan(
        plan_md=plan_md,
        tasks_path=tasks_path,
        source_week=source_week,
        default_priority=default_priority,
    )
    return {"created_count": created, "updated_count": updated, "tasks_path": tasks_path.as_posix()}


def tool_select_quiz_tasks(
    tasks_path: Path, n: int = 3, strategy: str = "priority+weakness"
) -> Dict[str, Any]:
    _ = strategy
    tasks = select_quiz_tasks(tasks_path, n=n)
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
